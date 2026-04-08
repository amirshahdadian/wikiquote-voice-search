"""
Automatic Speech Recognition (ASR) Service — mlx-whisper backend
Runs natively on Apple Silicon M-series via the MLX framework.
No CUDA required; uses GPU + Neural Engine through unified memory.

Install:  pip install mlx-whisper
Model:    mlx-community/whisper-large-v3-turbo  (~1.5 GB, 10-15x real-time on M3)
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default model — large-v3-turbo gives excellent quality at real-time speed
# on M3.  Use "mlx-community/whisper-small-mlx" for lower-latency demos.
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"

# Quote-search prompt steers the model toward vocabulary that appears in
# wikiquote queries ("Einstein", "courage", "wisdom", "find quotes about…")
_INITIAL_PROMPT = (
    "Find quotes about courage, wisdom, love, and happiness. "
    "Show me inspirational quotes by Einstein, Shakespeare, or Gandhi."
)


class ASRService:
    """
    ASR Service backed by mlx-whisper.

    mlx-whisper mirrors the openai-whisper Python API but executes entirely
    inside Apple's MLX framework, using the M-series GPU and Neural Engine
    without any MPS hacks or CUDA dependency.

    Public interface is identical to the previous NeMo/openai-whisper
    implementation so the orchestrator and backend need no changes.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "auto",   # kept for API compatibility; mlx handles device
        backend: str = "mlx",   # informational only
    ):
        self.model_name = model_name
        self.backend = "mlx"
        self._model_loaded = False
        logger.info("ASRService initialised (backend=mlx, model=%s)", model_name)

    # ------------------------------------------------------------------
    # Model loading — lazy; mlx-whisper caches the model after first call
    # ------------------------------------------------------------------
    def load_model(self) -> None:
        """Warm up the model so the first real request is not cold."""
        if self._model_loaded:
            return
        try:
            import mlx_whisper  # noqa: F401 — triggers model download/cache
            self._model_loaded = True
            logger.info("✅ mlx-whisper ready (model=%s)", self.model_name)
        except ImportError:
            logger.error(
                "mlx-whisper is not installed.  Run: pip install mlx-whisper"
            )
            raise

    # ------------------------------------------------------------------
    # Core transcription
    # ------------------------------------------------------------------
    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transcribe an audio file to text.

        Parameters
        ----------
        audio_path : str
            Path to any audio file (WAV, MP3, M4A, …).
        language : str, optional
            ISO 639-1 code, e.g. ``"en"``.  ``None`` = auto-detect.

        Returns
        -------
        dict with keys:
            text            – raw transcription string
            normalized_text – command-normalised version
            language        – detected / requested language code
            backend         – always ``"mlx"``
            segments        – list of timed segment dicts
        """
        import mlx_whisper

        logger.info("Transcribing: %s", audio_path)

        decode_opts: Dict[str, Any] = {
            "fp16": True,
            # mlx_whisper uses greedy decoding (temperature=0) — beam search
            # is not yet implemented in the MLX backend.
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

        logger.info("Transcription : %s", text)
        logger.info("Normalized    : %s", normalized)

        return {
            "text": text,
            "normalized_text": normalized,
            "language": result.get("language", language or "unknown"),
            "backend": "mlx",
            "segments": result.get("segments", []),
        }

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transcribe raw audio bytes by writing them to a temp file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            return self.transcribe(tmp_path, language=language)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------
    # Command normalisation
    # ------------------------------------------------------------------
    def normalize_command(self, text: str) -> str:
        """
        Clean up ASR transcription for downstream quote-search commands.

        Fixes common speech-recognition errors ("codes" → "quotes"),
        removes filler words, and extracts the core topic.
        """
        text = text.lower().strip()

        # Common ASR mishearings of "quotes"
        for wrong in [
            "codes", "code", "coats", "coat", "courts", "court",
            "colds", "cold", "cords", "cord", "cotes", "cote",
            "quoads", "quoad",
        ]:
            text = re.sub(rf"\b{wrong}\b", "quotes", text, flags=re.IGNORECASE)

        # Remove filler words
        for filler in [
            r"\bum+\b", r"\buh+\b", r"\blike\b", r"\byou know\b",
            r"\bi mean\b", r"\bso\b", r"\bwell\b", r"\bokay\b",
            r"\balright\b", r"\bactually\b",
        ]:
            text = re.sub(filler, "", text, flags=re.IGNORECASE)

        # Normalise command phrases
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

        # Extract meaningful topic words
        stop = {"find", "show", "give", "me", "quotes", "quote", "about", "on", "for"}
        words = [w for w in text.split() if w not in stop and len(w) > 2]
        if words:
            return " ".join(words)

        return " ".join(text.split())

    # ------------------------------------------------------------------
    # Compatibility helpers
    # ------------------------------------------------------------------
    def switch_backend(self, backend: str) -> None:
        """No-op: mlx-whisper is the only backend."""
        logger.info("switch_backend('%s') ignored — mlx is the only backend", backend)

    def get_backend_info(self) -> Dict[str, Any]:
        return {
            "active_backend": "mlx",
            "available_backends": {"mlx": True},
            "model_name": self.model_name,
            "device": "mlx (Apple Silicon GPU + Neural Engine)",
        }
