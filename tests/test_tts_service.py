"""Regression tests for the NeMo 2.x TTS wrapper."""
from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from services.tts_service import TTSService


class FakeTensor:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=np.float32)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._values


class FakeSpecModel:
    def parse(self, text: str):
        return f"tokens:{text}"

    def generate_spectrogram(self, tokens, **kwargs):
        return {"tokens": tokens, "kwargs": kwargs}


class FakeVocoder:
    def convert_spectrogram_to_audio(self, spec):
        return FakeTensor([[0.0, 0.1, -0.1]])


class TTSServiceTestCase(unittest.TestCase):
    def test_nemo_2_inference_path_does_not_require_nemo_infer(self) -> None:
        service = TTSService(device="cpu")
        service.spec_generator = FakeSpecModel()
        service.vocoder = FakeVocoder()

        with tempfile.NamedTemporaryFile(suffix=".wav") as output_file:
            waveform = service.synthesize("Knowledge is power.", output_path=output_file.name)

        self.assertEqual(waveform.shape, (3,))

    def test_personalized_synthesis_uses_preferences_without_nemo_infer(self) -> None:
        service = TTSService(device="cpu")
        service.spec_generator = FakeSpecModel()
        service.vocoder = FakeVocoder()

        preferences = {
            "pitch_scale": 1.2,
            "speaking_rate": 0.9,
            "energy_scale": 1.0,
            "style": "neutral",
        }

        with patch.object(service, "load_models", return_value=None):
            waveform = service.synthesize_personalized("Hello quote bot.", preferences=preferences)

        self.assertEqual(waveform.shape, (3,))


if __name__ == "__main__":
    unittest.main()
