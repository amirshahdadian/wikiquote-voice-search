from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any
from backend.config import settings
import os
import random
import re
import tempfile
from backend.config import Settings


# Sqlite Users

logger = logging.getLogger(__name__)
DEFAULT_DB_PATH = settings.resolved_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    group_identifier TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_tts_preferences (
    user_id TEXT PRIMARY KEY REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    speaking_rate REAL NOT NULL DEFAULT 1.0,
    energy_scale REAL NOT NULL DEFAULT 1.0,
    style TEXT NOT NULL DEFAULT 'neutral',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path | None = None) -> Path:
    path = Path(db_path or DEFAULT_DB_PATH)
    with get_connection(path) as connection:
        connection.executescript(_SCHEMA)
    return path


def save_user_profile(
    user_id: str,
    display_name: str,
    group_identifier: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_profiles (
                    user_id, display_name, group_identifier
                ) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    group_identifier = excluded.group_identifier,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, display_name, group_identifier),
            )
        return True
    except sqlite3.Error:
        logger.exception("Could not save user profile")
        return False


def get_user_profile(
    user_id: str, db_path: Path | None = None
) -> dict[str, Any] | None:
    try:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT user_id, display_name, group_identifier,
                       created_at, updated_at
                FROM user_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        logger.exception("Could not load user profile")
        return None


def list_user_profiles(db_path: Path | None = None) -> list[dict[str, Any]]:
    try:
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT user_id, display_name, group_identifier,
                       created_at, updated_at
                FROM user_profiles
                ORDER BY display_name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        logger.exception("Could not list user profiles")
        return []


def delete_user_profile(user_id: str, db_path: Path | None = None) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                "DELETE FROM user_profiles WHERE user_id = ?", (user_id,)
            )
        return True
    except sqlite3.Error:
        logger.exception("Could not delete user profile")
        return False


def save_tts_preferences(
    user_id: str,
    preferences: dict[str, Any],
    db_path: Path | None = None,
) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_tts_preferences (
                    user_id, speaking_rate, energy_scale, style
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    speaking_rate = excluded.speaking_rate,
                    energy_scale = excluded.energy_scale,
                    style = excluded.style,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    preferences.get("speaking_rate", 1.0),
                    preferences.get("energy_scale", 1.0),
                    preferences.get("style", "neutral"),
                ),
            )
        return True
    except sqlite3.Error:
        logger.exception("Could not save TTS preferences")
        return False


def get_tts_preferences(
    user_id: str, db_path: Path | None = None
) -> dict[str, Any] | None:
    try:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT speaking_rate, energy_scale, style
                FROM user_tts_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        logger.exception("Could not load TTS preferences")
        return None


def delete_tts_preferences(
    user_id: str, db_path: Path | None = None
) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                "DELETE FROM user_tts_preferences WHERE user_id = ?",
                (user_id,),
            )
        return True
    except sqlite3.Error:
        logger.exception("Could not delete TTS preferences")
        return False


# Users

class UserService:
    """Manage user profiles, embeddings, and personalized voice settings."""

    def __init__(self, app_settings: Settings, speaker_service: SpeakerIdentificationService):
        self.settings = app_settings
        self.speaker_service = speaker_service

        initialize_database(self.settings.resolved_db_path)
        self.settings.embeddings_dir.mkdir(parents=True, exist_ok=True)

    def list_users(self) -> list[dict[str, Any]]:
        known_ids = self._all_known_user_ids()
        users = [self._compose_user_profile(user_id) for user_id in known_ids]
        return sorted(users, key=lambda item: item["display_name"].lower())

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        if user_id not in self._all_known_user_ids():
            return None
        return self._compose_user_profile(user_id)

    def register_user(
        self,
        display_name: str,
        group_identifier: str | None,
        preferences: dict[str, Any],
        audio_samples: list[tuple[str, bytes]],
    ) -> dict[str, Any]:
        user_id = self._slugify_user_id(display_name)
        if not user_id:
            raise ValueError("Display name must contain letters or numbers")
        if user_id in self._all_known_user_ids():
            raise ValueError(f"User '{user_id}' already exists")
        if len(audio_samples) < 3:
            raise ValueError("At least 3 audio samples are required")

        preferences = dict(preferences)
        preferences["style"] = self._assign_unique_voice()
        sample_paths = self._materialize_uploads(audio_samples)
        try:
            embedding = self.speaker_service.enroll_speaker(user_id, sample_paths)
            self.speaker_service.save_embedding(
                embedding,
                str(self.settings.embeddings_dir / f"{user_id}.pkl"),
            )
            save_user_profile(user_id, display_name, group_identifier, self.settings.resolved_db_path)
            save_tts_preferences(user_id, preferences, self.settings.resolved_db_path)
            return self._compose_user_profile(user_id)
        finally:
            self._cleanup_paths(sample_paths)

    def re_enroll_user(
        self,
        user_id: str,
        audio_samples: list[tuple[str, bytes]],
    ) -> dict[str, Any]:
        profile = self.get_user(user_id)
        if profile is None:
            raise KeyError(f"Unknown user '{user_id}'")
        if len(audio_samples) < 3:
            raise ValueError("At least 3 audio samples are required")

        sample_paths = self._materialize_uploads(audio_samples)
        try:
            embedding = self.speaker_service.enroll_speaker(user_id, sample_paths)
            self.speaker_service.save_embedding(
                embedding,
                str(self.settings.embeddings_dir / f"{user_id}.pkl"),
            )
            return self._compose_user_profile(user_id)
        finally:
            self._cleanup_paths(sample_paths)

    def delete_user(self, user_id: str) -> None:
        if self.get_user(user_id) is None:
            raise KeyError(f"Unknown user '{user_id}'")

        embedding_path = self.settings.embeddings_dir / f"{user_id}.pkl"
        if embedding_path.exists():
            embedding_path.unlink()
        delete_tts_preferences(user_id, self.settings.resolved_db_path)
        delete_user_profile(user_id, self.settings.resolved_db_path)

    def load_recognized_user(self, user_id: str, confidence: float, source: str) -> dict[str, Any]:
        profile = self.get_user(user_id) or {"user_id": user_id, "display_name": user_id}
        return {
            "user_id": profile["user_id"],
            "display_name": profile["display_name"],
            "confidence": confidence,
            "source": source,
        }

    def _compose_user_profile(self, user_id: str) -> dict[str, Any]:
        profile = get_user_profile(user_id, self.settings.resolved_db_path)
        if profile is None:
            raise KeyError(f"Unknown user '{user_id}'")
        preferences = get_tts_preferences(user_id, self.settings.resolved_db_path)
        return {
            "user_id": user_id,
            "display_name": profile["display_name"],
            "group_identifier": profile.get("group_identifier"),
            "has_embedding": (self.settings.embeddings_dir / f"{user_id}.pkl").exists(),
            "preferences": preferences,
        }

    def _assign_unique_voice(self) -> str:
        from backend.voice import KOKORO_VOICES

        taken: set[str] = set()
        for uid in self._all_known_user_ids():
            prefs = get_tts_preferences(uid, self.settings.resolved_db_path)
            if prefs and prefs.get("style") in KOKORO_VOICES:
                taken.add(prefs["style"])
        available = [voice for voice in KOKORO_VOICES if voice not in taken]
        pool = available if available else list(KOKORO_VOICES)
        return random.choice(pool)

    def _all_known_user_ids(self) -> list[str]:
        return [
            profile["user_id"]
            for profile in list_user_profiles(self.settings.resolved_db_path)
        ]

    @staticmethod
    def _slugify_user_id(display_name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")

    def _materialize_uploads(self, samples: list[tuple[str, bytes]]) -> list[str]:
        temp_paths: list[str] = []
        for filename, payload in samples:
            suffix = Path(filename or "sample.wav").suffix or ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(payload)
                temp_paths.append(temp_file.name)
        return temp_paths

    @staticmethod
    def _cleanup_paths(paths: list[str]) -> None:
        for path in paths:
            if os.path.exists(path):
                os.unlink(path)
