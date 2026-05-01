"""Automatic speech recognition providers."""
from __future__ import annotations

import importlib.util
import logging
import os
import re
import tempfile
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_FASTER_MODEL = "Systran/faster-whisper-small"

# Quote-search prompt steers Whisper toward vocabulary that appears in
# wikiquote queries ("Einstein", "courage", "wisdom", "find quotes about...").
_INITIAL_PROMPT = (
    "Find quotes about courage, wisdom, love, and happiness. "
    "Show me inspirational quotes by Einstein, Shakespeare, or Gandhi."
)


class ASRProvider(ABC):
    """Common contract for speech-to-text backends."""

    backend: ClassVar[str]
    required_module: ClassVar[str]

    def __init__(self, model_name: str, device: str = "auto", compute_type: str | None = None):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model_loaded = False

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec(cls.required_module) is not None

    @abstractmethod
    def load_model(self) -> None:
        """Warm up the model or validate backend dependencies."""

    @abstractmethod
    def transcribe(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe an audio file to text."""

    def transcribe_bytes(self, audio_bytes: bytes, language: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe raw audio bytes by writing them to a temporary file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            return self.transcribe(tmp_path, language=language)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def normalize_command(self, text: str) -> str:
        """
        Clean up ASR transcription for downstream quote-search commands.

        Fixes common speech-recognition errors ("codes" -> "quotes"),
        removes filler words, and extracts the core topic.
        """
        text = text.lower().strip()

        for wrong in [
            "codes", "code", "coats", "coat", "courts", "court",
            "colds", "cold", "cords", "cord", "cotes", "cote",
            "quoads", "quoad",
        ]:
            text = re.sub(rf"\b{wrong}\b", "quotes", text, flags=re.IGNORECASE)

        for filler in [
            r"\bum+\b", r"\buh+\b", r"\blike\b", r"\byou know\b",
            r"\bi mean\b", r"\bso\b", r"\bwell\b", r"\bokay\b",
            r"\balright\b", r"\bactually\b",
        ]:
            text = re.sub(filler, "", text, flags=re.IGNORECASE)

        for pattern, replacement in [
            (r"find me some", "find"),
            (r"can you find", "find"),
            (r"i want to find", "find"),
            (r"i want", "find"),
            (r"show me some", "show me"),
            (r"give me some", "give me"),
            (r"search for", "find"),
            (r"look for", "find"),
        ]:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        stop = {"find", "show", "give", "me", "quotes", "quote", "about", "on", "for"}
        words = [word for word in text.split() if word not in stop and len(word) > 2]
        if words:
            return " ".join(words)

        return " ".join(text.split())

    def get_backend_info(self) -> Dict[str, Any]:
        return {
            "active_backend": self.backend,
            "model_name": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
        }


class MlxWhisperProvider(ASRProvider):
    """Apple Silicon ASR provider backed by mlx-whisper."""

    backend = "mlx"
    required_module = "mlx_whisper"

    def __init__(
        self,
        model_name: str = DEFAULT_MLX_MODEL,
        device: str = "auto",
        compute_type: str | None = None,
    ):
        super().__init__(model_name=model_name, device=device, compute_type=compute_type)
        logger.info("ASR provider initialised (backend=mlx, model=%s)", model_name)

    def load_model(self) -> None:
        if self._model_loaded:
            return
        try:
            import mlx_whisper  # noqa: F401
        except ImportError:
            logger.error("mlx-whisper is not installed. Install the mlx extra on Apple Silicon.")
            raise
        self._model_loaded = True
        logger.info("mlx-whisper ready (model=%s)", self.model_name)

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        import mlx_whisper

        logger.info("Transcribing with mlx-whisper: %s", audio_path)

        decode_opts: Dict[str, Any] = {
            "fp16": True,
            "temperature": 0.0,
            "initial_prompt": _INITIAL_PROMPT,
        }
        if language:
            decode_opts["language"] = language

        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=self.model_name,
            verbose=False,
            **decode_opts,
        )

        text = result["text"].strip()
        normalized = self.normalize_command(text)
        self._model_loaded = True

        return {
            "text": text,
            "normalized_text": normalized,
            "language": result.get("language", language or "unknown"),
            "backend": self.backend,
            "segments": result.get("segments", []),
        }

    def get_backend_info(self) -> Dict[str, Any]:
        info = super().get_backend_info()
        info["device"] = "mlx (Apple Silicon GPU + Neural Engine)"
        return info


class FasterWhisperProvider(ASRProvider):
    """Linux-friendly ASR provider backed by faster-whisper/CTranslate2."""

    backend = "faster"
    required_module = "faster_whisper"

    def __init__(
        self,
        model_name: str = DEFAULT_FASTER_MODEL,
        device: str = "cpu",
        compute_type: str | None = "int8",
        beam_size: int = 5,
    ):
        super().__init__(model_name=model_name, device=device, compute_type=compute_type or "int8")
        self.beam_size = beam_size
        self._model: Any | None = None
        logger.info(
            "ASR provider initialised (backend=faster, model=%s, device=%s, compute_type=%s)",
            model_name,
            self.device,
            self.compute_type,
        )

    def load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.error("faster-whisper is not installed. Install backend dependencies for Linux ASR.")
            raise

        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        self._model_loaded = True
        logger.info("faster-whisper ready (model=%s)", self.model_name)

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        self.load_model()
        assert self._model is not None

        logger.info("Transcribing with faster-whisper: %s", audio_path)

        segments_iter, info = self._model.transcribe(
            audio_path,
            language=language,
            beam_size=self.beam_size,
            temperature=0.0,
            initial_prompt=_INITIAL_PROMPT,
        )
        segments = list(segments_iter)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        normalized = self.normalize_command(text)

        return {
            "text": text,
            "normalized_text": normalized,
            "language": getattr(info, "language", language or "unknown"),
            "backend": self.backend,
            "segments": [self._segment_to_dict(segment) for segment in segments],
        }

    @staticmethod
    def _segment_to_dict(segment: Any) -> Dict[str, Any]:
        return {
            "id": getattr(segment, "id", None),
            "start": getattr(segment, "start", None),
            "end": getattr(segment, "end", None),
            "text": getattr(segment, "text", "").strip(),
            "avg_logprob": getattr(segment, "avg_logprob", None),
            "no_speech_prob": getattr(segment, "no_speech_prob", None),
        }

    def get_backend_info(self) -> Dict[str, Any]:
        info = super().get_backend_info()
        info["beam_size"] = self.beam_size
        return info


ASR_BACKENDS: dict[str, type[ASRProvider]] = {
    MlxWhisperProvider.backend: MlxWhisperProvider,
    FasterWhisperProvider.backend: FasterWhisperProvider,
}


def is_backend_available(backend: str) -> bool:
    provider_cls = ASR_BACKENDS.get(backend)
    return provider_cls.is_available() if provider_cls else False


def create_asr_provider(
    backend: str = "mlx",
    model_name: str | None = None,
    device: str = "auto",
    compute_type: str | None = None,
    beam_size: int = 5,
) -> ASRProvider:
    normalized_backend = backend.strip().lower()
    provider_cls = ASR_BACKENDS.get(normalized_backend)
    if provider_cls is None:
        valid = ", ".join(sorted(ASR_BACKENDS))
        raise ValueError(f"Unsupported ASR backend '{backend}'. Expected one of: {valid}")

    if provider_cls is MlxWhisperProvider:
        return MlxWhisperProvider(
            model_name=model_name or DEFAULT_MLX_MODEL,
            device=device,
            compute_type=compute_type,
        )

    faster_device = "cpu" if device == "auto" else device
    return FasterWhisperProvider(
        model_name=model_name or DEFAULT_FASTER_MODEL,
        device=faster_device,
        compute_type=compute_type or "int8",
        beam_size=beam_size,
    )


class ASRService(MlxWhisperProvider):
    """Backward-compatible name for code that imported the old MLX service."""
    pass
