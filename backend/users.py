from __future__ import annotations

import random
import re
import sqlite3
from pathlib import Path
from typing import Any

from backend.config import Settings


# Sqlite Users

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    group_identifier TEXT,
    speaking_rate REAL NOT NULL DEFAULT 1.0,
    energy_scale REAL NOT NULL DEFAULT 1.0,
    style TEXT NOT NULL DEFAULT 'neutral'
);
"""

_PREFERENCE_COLUMNS = ("speaking_rate", "energy_scale", "style")


def get_connection(db_path: Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path) -> Path:
    with get_connection(db_path) as connection:
        connection.executescript(_SCHEMA)
    return Path(db_path)


def get_tts_preferences(user_id: str, db_path: Path) -> dict[str, Any] | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT speaking_rate, energy_scale, style "
            "FROM user_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


# Users

class UserService:
    """Manage user profiles, voice vectors, and personalized speech settings."""

    def __init__(self, app_settings: Settings, speaker_service: Any):
        self.settings = app_settings
        self.speaker_service = speaker_service
        self.db_path = app_settings.resolved_db_path

        initialize_database(self.db_path)
        self.settings.embeddings_dir.mkdir(parents=True, exist_ok=True)

    def list_users(self) -> list[dict[str, Any]]:
        return [self._profile(row) for row in self._query("ORDER BY display_name COLLATE NOCASE")]

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        rows = self._query("WHERE user_id = ?", user_id)
        return self._profile(rows[0]) if rows else None

    def register_user(
        self,
        display_name: str,
        group_identifier: str | None,
        preferences: dict[str, Any],
        audio_samples: list[tuple[str, bytes]],
    ) -> dict[str, Any]:
        user_id = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
        if not user_id:
            raise ValueError("Display name must contain letters or numbers")
        if self.get_user(user_id) is not None:
            raise ValueError(f"User '{user_id}' already exists")

        self._save_embedding(user_id, audio_samples)
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_profiles (
                    user_id, display_name, group_identifier,
                    speaking_rate, energy_scale, style
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    display_name,
                    group_identifier,
                    preferences.get("speaking_rate", 1.0),
                    preferences.get("energy_scale", 1.0),
                    self._unused_voice(),
                ),
            )
        return self.get_user(user_id)

    def re_enroll_user(
        self,
        user_id: str,
        audio_samples: list[tuple[str, bytes]],
    ) -> dict[str, Any]:
        if self.get_user(user_id) is None:
            raise KeyError(f"Unknown user '{user_id}'")
        self._save_embedding(user_id, audio_samples)
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> None:
        if self.get_user(user_id) is None:
            raise KeyError(f"Unknown user '{user_id}'")

        self._embedding_path(user_id).unlink(missing_ok=True)
        with get_connection(self.db_path) as connection:
            connection.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))

    def load_recognized_user(self, user_id: str, confidence: float, source: str) -> dict[str, Any]:
        profile = self.get_user(user_id) or {"user_id": user_id, "display_name": user_id}
        return {
            "user_id": profile["user_id"],
            "display_name": profile["display_name"],
            "confidence": confidence,
            "source": source,
        }

    def _query(self, clause: str, *parameters: Any) -> list[sqlite3.Row]:
        with get_connection(self.db_path) as connection:
            return connection.execute(
                "SELECT user_id, display_name, group_identifier, "
                f"speaking_rate, energy_scale, style FROM user_profiles {clause}",
                parameters,
            ).fetchall()

    def _profile(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "user_id": row["user_id"],
            "display_name": row["display_name"],
            "group_identifier": row["group_identifier"],
            "has_embedding": self._embedding_path(row["user_id"]).exists(),
            "preferences": {column: row[column] for column in _PREFERENCE_COLUMNS},
        }

    def _embedding_path(self, user_id: str) -> Path:
        return self.settings.embeddings_dir / f"{user_id}.pkl"

    def _save_embedding(self, user_id: str, audio_samples: list[tuple[str, bytes]]) -> None:
        from backend.voice import write_temp_file

        paths = [write_temp_file(name, payload) for name, payload in audio_samples]
        try:
            embedding = self.speaker_service.enroll_speaker(paths)
            self.speaker_service.save_embedding(embedding, self._embedding_path(user_id))
        finally:
            for path in paths:
                Path(path).unlink(missing_ok=True)

    def _unused_voice(self) -> str:
        from backend.voice import KOKORO_VOICES

        with get_connection(self.db_path) as connection:
            taken = {
                row["style"]
                for row in connection.execute("SELECT style FROM user_profiles")
            }
        return random.choice([v for v in KOKORO_VOICES if v not in taken] or KOKORO_VOICES)
