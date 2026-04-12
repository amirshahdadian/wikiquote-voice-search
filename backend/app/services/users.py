"""User and profile management service."""
from __future__ import annotations

import os
import random
import re
import tempfile
from pathlib import Path
from typing import Any

from backend.app.core.settings import Settings
from backend.app.integrations.audio import KOKORO_VOICES, SpeakerIdentificationService
from backend.app.integrations.sqlite_users import (
    create_user,
    delete_tts_preferences,
    delete_user_profile,
    delete_user_record,
    get_tts_preferences,
    get_user_profile,
    initialize_database,
    list_tts_preference_users,
    list_user_profiles,
    save_tts_preferences,
    save_user_profile,
)


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
            create_user(user_id, self.settings.resolved_db_path)
            save_user_profile(user_id, display_name, group_identifier, self.settings.resolved_db_path)
            save_tts_preferences(user_id, preferences, self.settings.resolved_db_path)
            return self._compose_user_profile(user_id)
        finally:
            self._cleanup_paths(sample_paths)

    def update_user_preferences(self, user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        profile = self.get_user(user_id)
        if profile is None:
            raise KeyError(f"Unknown user '{user_id}'")
        save_tts_preferences(user_id, preferences, self.settings.resolved_db_path)
        return self._compose_user_profile(user_id)

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
        delete_user_record(user_id, self.settings.resolved_db_path)

    def load_recognized_user(self, user_id: str, confidence: float, source: str) -> dict[str, Any]:
        profile = self.get_user(user_id) or {"user_id": user_id, "display_name": user_id}
        return {
            "user_id": profile["user_id"],
            "display_name": profile["display_name"],
            "confidence": confidence,
            "source": source,
        }

    def _compose_user_profile(self, user_id: str) -> dict[str, Any]:
        profile = get_user_profile(user_id, self.settings.resolved_db_path) or {
            "user_id": user_id,
            "display_name": user_id,
            "group_identifier": None,
        }
        preferences = get_tts_preferences(user_id, self.settings.resolved_db_path)
        return {
            "user_id": user_id,
            "display_name": profile["display_name"],
            "group_identifier": profile.get("group_identifier"),
            "has_embedding": (self.settings.embeddings_dir / f"{user_id}.pkl").exists(),
            "preferences": preferences,
        }

    def _assign_unique_voice(self) -> str:
        taken: set[str] = set()
        for uid in self._all_known_user_ids():
            prefs = get_tts_preferences(uid, self.settings.resolved_db_path)
            if prefs and prefs.get("style") in KOKORO_VOICES:
                taken.add(prefs["style"])
        available = [voice for voice in KOKORO_VOICES if voice not in taken]
        pool = available if available else list(KOKORO_VOICES)
        return random.choice(pool)

    def _all_known_user_ids(self) -> list[str]:
        user_ids = {profile["user_id"] for profile in list_user_profiles(self.settings.resolved_db_path)}
        user_ids.update(list_tts_preference_users(self.settings.resolved_db_path))
        user_ids.update(path.stem for path in self.settings.embeddings_dir.glob("*.pkl"))
        return sorted(user_ids)

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

