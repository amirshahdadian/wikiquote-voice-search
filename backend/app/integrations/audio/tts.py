"""Personalized speech synthesis with Kokoro ONNX."""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from backend.app.integrations.sqlite_users import get_tts_preferences

logger = logging.getLogger(__name__)

KOKORO_VOICES = [
    "af_heart",
    "af_bella",
    "af_nicole",
    "af_sarah",
    "af_sky",
    "af_alloy",
    "af_aoede",
    "af_jessica",
    "af_kore",
    "af_nova",
    "af_river",
    "am_adam",
    "am_michael",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_onyx",
    "am_puck",
    "bf_emma",
    "bf_isabella",
    "bf_alice",
    "bf_lily",
    "bm_george",
    "bm_lewis",
    "bm_daniel",
    "bm_fable",
]

DEFAULT_VOICE = "af_heart"
MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/"
    "download/model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/"
    "download/model-files-v1.0/voices-v1.0.bin"
)


class TTSService:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path
        self._kokoro: Any | None = None

    def load_models(self) -> None:
        if self._kokoro is not None:
            return
        from kokoro_onnx import Kokoro

        cache = Path.home() / ".cache" / "kokoro_onnx"
        cache.mkdir(parents=True, exist_ok=True)
        model = cache / "kokoro-v1.0.onnx"
        voices = cache / "voices-v1.0.bin"
        for path, url in ((model, MODEL_URL), (voices, VOICES_URL)):
            if not path.exists():
                logger.info("Downloading Kokoro asset file=%s", path.name)
                urllib.request.urlretrieve(url, path)
        self._kokoro = Kokoro(str(model), str(voices))

    def synthesize_personalized(
        self,
        text: str,
        user_id: str | None = None,
        output_path: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> np.ndarray:
        selected = preferences or self._preferences(user_id)
        voice = str(selected.get("style") or DEFAULT_VOICE)
        if voice not in KOKORO_VOICES:
            voice = DEFAULT_VOICE
        speed = float(selected.get("speaking_rate") or 1.0)
        energy = float(selected.get("energy_scale") or 1.0)

        self.load_models()
        samples, sample_rate = self._kokoro.create(
            text,
            voice=voice,
            speed=speed,
            lang="en-us",
        )
        audio = np.clip(
            np.asarray(samples, dtype=np.float32) * energy,
            -1.0,
            1.0,
        )
        if output_path:
            sf.write(output_path, audio, int(sample_rate))
        logger.info(
            "event=tts voice=%s sample_rate=%d samples=%d",
            voice,
            sample_rate,
            len(audio),
        )
        return audio

    def _preferences(self, user_id: str | None) -> dict[str, Any]:
        defaults = {
            "speaking_rate": 1.0,
            "energy_scale": 1.0,
            "style": DEFAULT_VOICE,
        }
        if not user_id or not self.db_path:
            return defaults
        return {
            **defaults,
            **(get_tts_preferences(user_id, Path(self.db_path)) or {}),
        }
