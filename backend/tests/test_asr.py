from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

from backend.app.integrations.audio.asr import ASRService


def test_transcription_is_not_rewritten_or_logged(monkeypatch, caplog):
    transcript = "Um, find me quotes about courage"
    fake_whisper = SimpleNamespace(
        transcribe=lambda *args, **kwargs: {
            "text": transcript,
            "language": "en",
            "segments": [],
        }
    )
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake_whisper)

    with caplog.at_level(logging.INFO):
        result = ASRService().transcribe("sample.wav")

    assert result["normalized_text"] == transcript
    assert transcript not in caplog.text
