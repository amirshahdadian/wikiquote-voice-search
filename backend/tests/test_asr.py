from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

from backend.voice import transcribe


def test_transcription_is_not_rewritten_or_logged(monkeypatch, caplog):
    spoken = "Um, find me quotes about courage"
    calls = {}

    def fake_transcribe(path, **kwargs):
        calls.update(kwargs)
        return {"text": f"  {spoken}  ", "language": "en", "segments": []}

    monkeypatch.setitem(
        sys.modules, "mlx_whisper", SimpleNamespace(transcribe=fake_transcribe)
    )

    with caplog.at_level(logging.INFO):
        result = transcribe("sample.wav")

    assert result == spoken
    assert spoken not in caplog.text
    assert calls["temperature"] == 0.0
    assert "quotes" in calls["initial_prompt"]
