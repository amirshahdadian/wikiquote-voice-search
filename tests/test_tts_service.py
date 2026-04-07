"""
Tests for the kokoro-onnx TTS service.

The Kokoro model is ~310 MB — these tests mock the model to keep the suite fast
and dependency-free.  Synthesis correctness is covered by the smoke test in CI.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from services.tts_service import TTSService, DEFAULT_VOICE, KOKORO_VOICES, SAMPLE_RATE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_service_with_mock_kokoro(voice_call_result=None) -> TTSService:
    """Return a TTSService whose internal Kokoro is replaced by a MagicMock."""
    if voice_call_result is None:
        voice_call_result = (np.zeros(100, dtype=np.float32), SAMPLE_RATE)

    svc = TTSService()
    mock_kokoro = MagicMock()
    mock_kokoro.create.return_value = voice_call_result
    svc._kokoro = mock_kokoro          # inject — bypasses load_models()
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TTSServiceInitTest(unittest.TestCase):

    def test_init_does_not_load_model_eagerly(self):
        """Model should not be loaded at construction time (lazy init)."""
        svc = TTSService()
        self.assertIsNone(svc._kokoro)

    def test_backend_info(self):
        info = TTSService().get_backend_info()
        self.assertEqual(info["backend"], "kokoro-onnx")
        self.assertEqual(info["sample_rate"], SAMPLE_RATE)
        self.assertIn(DEFAULT_VOICE, info["voices"])

    def test_default_preferences(self):
        prefs = TTSService._default_preferences()
        self.assertEqual(prefs["style"], DEFAULT_VOICE)
        self.assertAlmostEqual(prefs["speaking_rate"], 1.0)


class TTSServiceSynthesisTest(unittest.TestCase):

    def test_synthesize_returns_float32_array(self):
        """synthesize() should return a 1-D float32 numpy array."""
        fake_audio = np.linspace(-0.5, 0.5, 2400, dtype=np.float32)
        svc = _make_service_with_mock_kokoro((fake_audio, SAMPLE_RATE))

        result = svc.synthesize("Hello world.")
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.dtype, np.float32)
        self.assertEqual(result.ndim, 1)

    def test_synthesize_clips_to_minus_one_plus_one(self):
        """synthesize() must clip audio to [-1, 1]."""
        loud = np.full(100, 5.0, dtype=np.float32)   # exceeds [-1, 1]
        svc = _make_service_with_mock_kokoro((loud, SAMPLE_RATE))

        result = svc.synthesize("Loud text.")
        self.assertLessEqual(result.max(), 1.0)
        self.assertGreaterEqual(result.min(), -1.0)

    def test_synthesize_writes_wav_file(self):
        """synthesize(output_path=...) must produce a valid WAV file."""
        import soundfile as sf
        fake_audio = np.zeros(4800, dtype=np.float32)
        svc = _make_service_with_mock_kokoro((fake_audio, SAMPLE_RATE))

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
            out_path = fh.name
        try:
            svc.synthesize("Test.", output_path=out_path)
            info = sf.info(out_path)
            self.assertEqual(info.samplerate, SAMPLE_RATE)
            self.assertGreater(info.frames, 0)
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)


class TTSServicePersonalizationTest(unittest.TestCase):

    def test_synthesize_personalized_uses_style_as_voice(self):
        """synthesize_personalized must pass the 'style' preference as voice."""
        svc = _make_service_with_mock_kokoro()
        prefs = {
            "style": "bm_george",
            "speaking_rate": 1.2,
            "energy_scale": 1.0,
        }
        svc.synthesize_personalized("Quote text.", preferences=prefs)
        call_kwargs = svc._kokoro.create.call_args.kwargs
        self.assertEqual(call_kwargs["voice"], "bm_george")

    def test_synthesize_personalized_uses_speaking_rate_as_speed(self):
        """synthesize_personalized must forward speaking_rate as Kokoro speed."""
        svc = _make_service_with_mock_kokoro()
        prefs = {
            "style": "af_heart",
            "speaking_rate": 0.85,
            "energy_scale": 1.0,
        }
        svc.synthesize_personalized("Quote text.", preferences=prefs)
        call_kwargs = svc._kokoro.create.call_args.kwargs
        self.assertAlmostEqual(call_kwargs["speed"], 0.85, places=3)

    def test_synthesize_personalized_applies_energy_scale(self):
        """energy_scale multiplies the raw audio."""
        base = np.full(100, 0.4, dtype=np.float32)
        svc = _make_service_with_mock_kokoro((base, SAMPLE_RATE))
        prefs = {
            "style": "af_heart",
            "speaking_rate": 1.0,
            "energy_scale": 0.5,   # halve the volume
        }
        result = svc.synthesize_personalized("Quote.", preferences=prefs)
        self.assertAlmostEqual(float(result.max()), 0.2, places=3)

    def test_synthesize_personalized_unknown_voice_falls_back(self):
        """Unknown voice preset should fall back to DEFAULT_VOICE gracefully."""
        svc = _make_service_with_mock_kokoro()
        prefs = {
            "style": "xx_unknown_voice",
            "speaking_rate": 1.0,
            "energy_scale": 1.0,
        }
        # Should not raise
        svc.synthesize_personalized("Quote.", preferences=prefs)
        call_kwargs = svc._kokoro.create.call_args.kwargs
        self.assertEqual(call_kwargs["voice"], DEFAULT_VOICE)

    def test_synthesize_personalized_uses_defaults_when_no_prefs(self):
        """synthesize_personalized() with no user_id uses default voice/speed."""
        svc = _make_service_with_mock_kokoro()
        svc.synthesize_personalized("Quote.")
        call_kwargs = svc._kokoro.create.call_args.kwargs
        self.assertEqual(call_kwargs["voice"], DEFAULT_VOICE)
        self.assertAlmostEqual(call_kwargs["speed"], 1.0)

    def test_voice_preset_rotation(self):
        """assign_voice_preset cycles through distinct voices."""
        presets = [TTSService.assign_voice_preset(i) for i in range(len(KOKORO_VOICES))]
        self.assertEqual(len(set(presets)), len(KOKORO_VOICES))


if __name__ == "__main__":
    unittest.main()
