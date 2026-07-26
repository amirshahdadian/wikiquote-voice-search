import logging

import numpy as np
import pytest

from backend.app.integrations.audio.tts import TTSService


class FakeKokoro:
    def __init__(self, error=None):
        self.error = error

    def create(self, text, *, voice, speed, lang):
        if self.error:
            raise self.error
        return np.zeros(24, dtype=np.float32), 24_000


def test_tts_logs_metadata_without_spoken_text(caplog):
    service = TTSService()
    service._kokoro = FakeKokoro()

    with caplog.at_level(logging.INFO):
        audio = service.synthesize_personalized(
            "private quotation text",
            preferences={
                "style": "af_heart",
                "speaking_rate": 1.0,
                "energy_scale": 1.0,
            },
        )

    assert len(audio) == 24
    assert "private quotation text" not in caplog.text


def test_kokoro_error_reaches_voice_service():
    service = TTSService()
    service._kokoro = FakeKokoro(RuntimeError("offline"))

    with pytest.raises(RuntimeError, match="offline"):
        service.synthesize_personalized("hello")
