"""Voice-related application service."""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from typing import Any

from backend.app.core.settings import Settings
from backend.app.integrations.audio import ASRService, SimpleTTSService, SpeakerIdentificationService, TTSService


class VoiceService:
    """Manage audio transcription, speaker recognition, and synthesis."""

    def __init__(
        self,
        app_settings: Settings,
        speaker_service: SpeakerIdentificationService | None = None,
        asr_service: ASRService | None = None,
        tts_service: TTSService | None = None,
        tts_fallback: SimpleTTSService | None = None,
    ):
        self.settings = app_settings
        self._speaker_service = speaker_service or SpeakerIdentificationService(threshold=0.75)
        self._asr_service = asr_service
        self._tts_service = tts_service
        self._tts_fallback = tts_fallback
        self.settings.generated_audio_dir.mkdir(parents=True, exist_ok=True)

    @property
    def speaker_service(self) -> SpeakerIdentificationService:
        return self._speaker_service

    @property
    def asr_service(self) -> ASRService:
        if self._asr_service is None:
            self._asr_service = ASRService()
        return self._asr_service

    @property
    def tts_service(self) -> TTSService:
        if self._tts_service is None:
            self._tts_service = TTSService(device="cpu", db_path=str(self.settings.resolved_db_path))
        return self._tts_service

    @property
    def tts_fallback(self) -> SimpleTTSService:
        if self._tts_fallback is None:
            self._tts_fallback = SimpleTTSService(device="cpu", db_path=str(self.settings.resolved_db_path))
        return self._tts_fallback

    def health_flags(self, search_ready: bool) -> dict[str, bool]:
        return {
            "search": search_ready,
            "asr": importlib.util.find_spec("mlx_whisper") is not None,
            "speaker_id": importlib.util.find_spec("resemblyzer") is not None,
            "tts": (
                importlib.util.find_spec("kokoro_onnx") is not None
                or importlib.util.find_spec("gtts") is not None
            ),
            "sqlite": self.settings.resolved_db_path.exists(),
        }

    def transcribe_bytes(self, audio_bytes: bytes, filename: str) -> tuple[str, str]:
        temp_path = self.write_temp_file(filename, audio_bytes)
        try:
            result = self.asr_service.transcribe(temp_path)
            transcript = result["text"].strip()
            normalized = result.get("normalized_text", transcript).strip()
            return transcript, normalized
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def identify_speaker(self, audio_bytes: bytes, filename: str) -> tuple[str | None, float]:
        temp_path = self.write_temp_file(filename, audio_bytes)
        try:
            enrolled_users = self.speaker_service.load_all_embeddings(str(self.settings.embeddings_dir))
            if not enrolled_users:
                return None, 0.0
            return self.speaker_service.identify_speaker(temp_path, enrolled_users)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def synthesize_audio(
        self,
        text: str,
        user_id: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> tuple[str | None, list[str]]:
        warnings: list[str] = []
        primary_filename = f"{uuid.uuid4().hex}.wav"
        primary_path = self.settings.generated_audio_dir / primary_filename
        try:
            self.tts_service.synthesize_personalized(
                text=text,
                user_id=user_id,
                output_path=str(primary_path),
                preferences=preferences,
            )
            return self.audio_url_for(primary_filename), warnings
        except Exception:
            warnings.append("tts_fallback")

        fallback_filename = f"{uuid.uuid4().hex}.mp3"
        fallback_path = self.settings.generated_audio_dir / fallback_filename
        try:
            self.tts_fallback.synthesize_personalized(
                text=text,
                user_id=user_id,
                output_path=str(fallback_path),
                preferences=preferences,
            )
            return self.audio_url_for(fallback_filename), warnings
        except Exception:
            warnings.append("tts_unavailable")
            return None, warnings

    def resolve_audio_path(self, audio_id: str) -> Path | None:
        candidate = (self.settings.generated_audio_dir / audio_id).resolve()
        try:
            candidate.relative_to(self.settings.generated_audio_dir.resolve())
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    def create_tts_preview(
        self,
        text: str,
        user_id: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audio_url, warnings = self.synthesize_audio(text=text, user_id=user_id, preferences=preferences)
        return {"audio_url": audio_url, "warnings": warnings}

    def audio_url_for(self, audio_id: str) -> str:
        return f"{self.settings.api_prefix}/audio/{audio_id}"

    @staticmethod
    def write_temp_file(filename: str, payload: bytes) -> str:
        suffix = Path(filename or "sample.wav").suffix or ".wav"
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(payload)
            return temp_file.name

