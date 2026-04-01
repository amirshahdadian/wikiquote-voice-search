"""Runtime settings for the FastAPI backend."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.wikiquote_voice.config import Config


def _parse_origins(raw_value: str | None) -> list[str]:
    if not raw_value:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


@dataclass(slots=True)
class AppSettings:
    api_prefix: str = "/api"
    frontend_origins: list[str] = field(
        default_factory=lambda: _parse_origins(os.getenv("FRONTEND_ORIGINS"))
    )
    generated_audio_dir: Path = field(
        default_factory=lambda: Config.DATA_DIR / "api_audio"
    )
    embeddings_dir: Path = field(
        default_factory=lambda: Config.DATA_DIR / "embeddings"
    )
    conversation_history_limit: int = int(os.getenv("CONVERSATION_HISTORY_LIMIT", "8"))


settings = AppSettings()
