"""Helpers for loading NeMo 2.x voice models with stable project defaults."""
from __future__ import annotations

import platform
from typing import Optional

from .config import Config


def is_apple_silicon() -> bool:
    """Return True when running on Apple Silicon macOS."""
    return platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}


def resolve_runtime_device(device: str, allow_mps: bool = False) -> str:
    """
    Resolve a requested device without importing torch eagerly.

    On Apple Silicon, ``auto`` prefers ``mps`` for PyTorch-native models when
    ``allow_mps`` is enabled.
    """
    normalized = (device or "auto").lower()
    valid_devices = {"auto", "cpu", "cuda"}
    if allow_mps:
        valid_devices.add("mps")

    if normalized not in valid_devices:
        return "cpu"
    if normalized != "auto":
        return normalized
    if allow_mps and is_apple_silicon():
        return "mps"
    return "cpu"


def resolve_nemo_device(device: str) -> str:
    """
    Resolve a requested device to a stable runtime device string.

    This helper intentionally avoids importing torch during module import or
    service construction, because some environments abort when torch is loaded.
    """
    return resolve_runtime_device(device, allow_mps=False)


def get_nemo_asr_model_name(language: Optional[str] = None) -> str:
    """Select the configured NeMo ASR model for the requested language."""
    normalized = (language or "").lower().strip()
    if normalized and normalized != "en" and Config.NEMO_ASR_MULTILINGUAL_MODEL:
        return Config.NEMO_ASR_MULTILINGUAL_MODEL
    return Config.NEMO_ASR_MODEL


def load_nemo_tts_spec_model(device: str):
    """Load the configured NeMo 2.x FastPitch-style spectrogram model."""
    from nemo.collections.tts.models import FastPitchModel

    resolved_device = resolve_nemo_device(device)
    model = FastPitchModel.from_pretrained(
        model_name=Config.NEMO_TTS_SPEC_MODEL,
        map_location=resolved_device,
    )
    model.eval()
    return model.to(resolved_device)


def load_nemo_tts_vocoder(device: str):
    """Load the configured NeMo 2.x HiFiGAN vocoder."""
    from nemo.collections.tts.models import HifiGanModel

    resolved_device = resolve_nemo_device(device)
    model = HifiGanModel.from_pretrained(
        model_name=Config.NEMO_TTS_VOCODER_MODEL,
        map_location=resolved_device,
    )
    model.eval()
    return model.to(resolved_device)


def load_nemo_speaker_model(device: str):
    """Load the configured NeMo 2.x speaker verification model."""
    from nemo.collections.asr.models import EncDecSpeakerLabelModel

    resolved_device = resolve_nemo_device(device)
    model = EncDecSpeakerLabelModel.from_pretrained(
        model_name=Config.NEMO_SPEAKER_MODEL,
        map_location=resolved_device,
    )
    model.eval()
    return model.to(resolved_device)


def load_nemo_asr_model(device: str, language: Optional[str] = None):
    """Load the configured NeMo 2.x ASR model."""
    import nemo.collections.asr as nemo_asr

    resolved_device = resolve_nemo_device(device)
    model_name = get_nemo_asr_model_name(language)
    model = nemo_asr.models.ASRModel.from_pretrained(
        model_name=model_name,
        map_location=resolved_device,
    )
    model.eval()
    return model.to(resolved_device)
