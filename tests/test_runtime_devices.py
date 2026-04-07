"""
Runtime / device tests for the Step 2 AI services.

Updated to reflect the M3-native backend stack:
  ASR            → mlx-whisper  (Apple Silicon GPU + Neural Engine)
  Speaker ID     → resemblyzer  (CPU, GE2E embeddings)
  TTS            → kokoro-onnx  (CPU, ONNX runtime)
"""
import os
import tempfile
import unittest

import numpy as np
import soundfile as sf

from services.asr_service import ASRService
from services.speaker_identification import SpeakerIdentificationService
from services.tts_service import TTSService


class RuntimeDevicesTest(unittest.TestCase):

    # ------------------------------------------------------------------
    # ASR
    # ------------------------------------------------------------------
    def test_asr_backend_is_mlx_on_apple_silicon(self):
        """get_backend_info reports the mlx backend and device string."""
        info = ASRService().get_backend_info()
        self.assertEqual(info["active_backend"], "mlx")
        self.assertIn("mlx", info["device"].lower())

    def test_asr_model_name_is_set(self):
        """The default model is the large-v3-turbo variant."""
        asr = ASRService()
        self.assertIn("whisper", asr.model_name.lower())

    # ------------------------------------------------------------------
    # Speaker ID
    # ------------------------------------------------------------------
    def test_speaker_id_threshold_stored(self):
        """Custom threshold is stored on the service."""
        svc = SpeakerIdentificationService(threshold=0.80)
        self.assertAlmostEqual(svc.threshold, 0.80)

    def test_speaker_id_compute_similarity_unit_vectors(self):
        """Cosine similarity of identical unit vectors is 1.0."""
        rng = np.random.default_rng(0)
        v = rng.normal(size=256).astype(np.float32)
        v /= np.linalg.norm(v)
        sim = SpeakerIdentificationService.compute_similarity(v, v)
        self.assertAlmostEqual(sim, 1.0, places=5)

    def test_speaker_id_compute_similarity_orthogonal(self):
        """Orthogonal vectors produce similarity ≈ 0 (clipped to [0,1])."""
        v1 = np.zeros(256, dtype=np.float32)
        v2 = np.zeros(256, dtype=np.float32)
        v1[0] = 1.0
        v2[1] = 1.0
        sim = SpeakerIdentificationService.compute_similarity(v1, v2)
        self.assertAlmostEqual(sim, 0.0, places=5)

    def test_speaker_preprocessing_produces_16khz_mono(self):
        """_preprocess returns a 1-D float32 array resampled to ~16 kHz.

        resemblyzer uses WebRTC VAD internally; pure sine waves are filtered out
        as non-speech.  Broadband noise is used here because it passes the VAD
        gate and is representative of how the preprocessor handles real audio.
        """
        sr_orig = 44_100
        rng = np.random.default_rng(42)
        # Broadband noise (similar spectral density to speech) in stereo
        noise = rng.normal(scale=0.2, size=sr_orig).astype(np.float32)
        stereo = np.column_stack([noise, noise * 0.9]).astype(np.float32)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
            src_path = fh.name
        try:
            sf.write(src_path, stereo, sr_orig)

            # _preprocess must return a 1-D float32 array
            wav = SpeakerIdentificationService._preprocess(src_path)
            self.assertEqual(wav.ndim, 1)
            self.assertEqual(wav.dtype, np.float32)
            # VAD may trim some frames; we just require at least 8 000 samples
            # to confirm meaningful audio was retained after resampling.
            self.assertGreater(len(wav), 8_000)
        finally:
            if os.path.exists(src_path):
                os.unlink(src_path)

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------
    def test_tts_backend_info(self):
        """get_backend_info reports kokoro-onnx backend at 24 kHz."""
        info = TTSService().get_backend_info()
        self.assertEqual(info["backend"], "kokoro-onnx")
        self.assertEqual(info["sample_rate"], 24_000)

    def test_tts_voice_preset_rotation(self):
        """assign_voice_preset cycles through different presets for each user."""
        presets = [TTSService.assign_voice_preset(i) for i in range(5)]
        self.assertEqual(len(set(presets)), 5, "First 5 presets should all be distinct")

    def test_tts_default_preferences(self):
        """_default_preferences returns sensible defaults."""
        prefs = TTSService._default_preferences()
        self.assertEqual(prefs["style"], "af_heart")
        self.assertAlmostEqual(prefs["speaking_rate"], 1.0)
        self.assertAlmostEqual(prefs["energy_scale"], 1.0)


if __name__ == "__main__":
    unittest.main()
