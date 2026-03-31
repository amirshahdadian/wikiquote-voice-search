import unittest
import os
import tempfile

import numpy as np
import soundfile as sf

from services.asr_service import ASRService
from services.speaker_identification import SpeakerIdentificationService
from services.tts_service import TTSService
from src.wikiquote_voice.nemo_compat import is_apple_silicon, resolve_nemo_device


class RuntimeDevicesTest(unittest.TestCase):
    def test_nemo_services_default_to_cpu(self):
        self.assertEqual(TTSService(device="auto").device, "cpu")
        self.assertEqual(SpeakerIdentificationService(device="auto").device, "cpu")
        self.assertEqual(resolve_nemo_device("auto"), "cpu")

    def test_asr_auto_prefers_supported_runtime(self):
        info = ASRService(backend="auto").get_backend_info()
        expected_device = "mps" if is_apple_silicon() else "cpu"
        self.assertEqual(info["device"], expected_device)

    def test_speaker_audio_is_normalized_to_mono_16khz(self):
        service = SpeakerIdentificationService(device="auto")

        sample_rate = 44100
        duration_seconds = 1
        time_axis = np.linspace(0, duration_seconds, sample_rate * duration_seconds, endpoint=False)
        stereo_waveform = np.stack(
            [
                0.2 * np.sin(2 * np.pi * 220 * time_axis),
                0.2 * np.sin(2 * np.pi * 330 * time_axis),
            ],
            axis=1,
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as src_file:
            source_path = src_file.name

        try:
            sf.write(source_path, stereo_waveform, sample_rate)
            normalized_path = service._prepare_audio_for_embedding(source_path)
            normalized_waveform, normalized_sr = sf.read(normalized_path, always_2d=False)

            self.assertEqual(normalized_sr, 16000)
            self.assertEqual(normalized_waveform.ndim, 1)
        finally:
            if os.path.exists(source_path):
                os.unlink(source_path)
            if 'normalized_path' in locals() and os.path.exists(normalized_path):
                os.unlink(normalized_path)


if __name__ == "__main__":
    unittest.main()
