"""Speech transcription through mlx-whisper."""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
_INITIAL_PROMPT = (
    "Find quotes about courage, wisdom, love, and happiness. "
    "Show me quotes by Einstein, Shakespeare, or Gandhi."
)


class ASRService:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "auto",
        backend: str = "mlx",
    ):
        self.model_name = model_name
        self._model_loaded = False

    def load_model(self) -> None:
        if self._model_loaded:
            return
        try:
            import mlx_whisper  # noqa: F401
        except ImportError:
            logger.error("mlx-whisper is not installed")
            raise
        self._model_loaded = True

    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        import mlx_whisper

        options: dict[str, Any] = {
            "fp16": True,
            "temperature": 0.0,
            "initial_prompt": _INITIAL_PROMPT,
        }
        if language:
            options["language"] = language

        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=self.model_name,
            verbose=False,
            **options,
        )
        text = result["text"].strip()
        self._model_loaded = True
        logger.info("Transcription completed")
        return {
            "text": text,
            "language": result.get("language", language or "unknown"),
            "backend": "mlx",
            "segments": result.get("segments", []),
        }

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        language: str | None = None,
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(audio_bytes)
            path = temp_file.name
        try:
            return self.transcribe(path, language=language)
        finally:
            if os.path.exists(path):
                os.remove(path)
