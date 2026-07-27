from __future__ import annotations

import logging
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# Logging

def configure_logging(level: str) -> None:
    """Configure application logging once at startup."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logging.getLogger().setLevel(level.upper())


def log_model_event(
    *,
    model: str,
    intent: str,
    latency_ms: int,
    fallback: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """Log model telemetry without request or response content."""
    logging.getLogger("backend.models").info(
        "model=%s intent=%s latency_ms=%d input_tokens=%s output_tokens=%s fallback=%s",
        model, intent, latency_ms, input_tokens, output_tokens, fallback,
    )


# Settings

class Settings(BaseSettings):
    """Canonical runtime settings for the FastAPI backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    frontend_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    neo4j_uri: str = "neo4j://127.0.0.1:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "neo4j"

    gemini_api_key: SecretStr | None = None
    gemini_llm_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = Field(default=15.0, ge=10.0)
    gemini_max_retries: int = 2

    batch_size: int = 1000
    log_level: str = "INFO"
    parse_page_limit: int | None = None

    data_dir: Path = Path("data")
    db_path: Path = Path("data/wikiquote_voice.db")
    xml_file: Path = Path("enwikiquote-20250601-pages-articles.xml")

    @property
    def resolved_db_path(self) -> Path:
        return self.db_path.expanduser()

    @property
    def generated_audio_dir(self) -> Path:
        return (self.data_dir / "api_audio").expanduser()

    @property
    def embeddings_dir(self) -> Path:
        return (self.data_dir / "embeddings").expanduser()


settings = Settings()
