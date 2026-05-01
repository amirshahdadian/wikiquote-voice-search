from __future__ import annotations

import pytest

from backend.app.integrations.audio.asr import (
    FasterWhisperProvider,
    MlxWhisperProvider,
    create_asr_provider,
)


def test_create_mlx_provider():
    provider = create_asr_provider(backend="mlx")
    assert isinstance(provider, MlxWhisperProvider)
    assert provider.backend == "mlx"


def test_create_faster_provider_defaults_to_cpu_int8():
    provider = create_asr_provider(backend="faster")
    assert isinstance(provider, FasterWhisperProvider)
    assert provider.backend == "faster"
    assert provider.device == "cpu"
    assert provider.compute_type == "int8"


def test_create_provider_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unsupported ASR backend"):
        create_asr_provider(backend="unknown")


def test_command_normalization_is_shared_across_providers():
    provider = create_asr_provider(backend="faster")
    assert provider.normalize_command("Can you find me some codes about courage") == "courage"
