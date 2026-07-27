from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# Logging

def configure_logging(level: str) -> None:
    """Configure application logging once at startup."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level.upper())
        return

    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def log_model_event(
    *,
    event: Literal["query", "embedding"],
    model: str,
    latency_ms: int,
    fallback: str,
    intent: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    dimensions: int | None = None,
) -> None:
    """Log model telemetry without request or response content."""
    fields = [f"event={event}", f"model={model}"]
    if intent is not None:
        fields.append(f"intent={intent}")
    if dimensions is not None:
        fields.append(f"dimensions={dimensions}")
    fields.append(f"latency_ms={latency_ms}")
    if input_tokens is not None:
        fields.append(f"input_tokens={input_tokens}")
    if output_tokens is not None:
        fields.append(f"output_tokens={output_tokens}")
    fields.append(f"fallback={fallback}")
    logging.getLogger("backend.models").info(" ".join(fields))


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
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dimensions: int = Field(default=768, ge=768, le=768)
    gemini_timeout_seconds: float = Field(default=15.0, ge=10.0)
    gemini_max_retries: int = 2

    batch_size: int = 1000
    log_level: str = "INFO"
    parse_page_limit: int | None = None

    data_dir: Path = Path("data")
    artifacts_dir: Path = Path("artifacts")
    db_path: Path | None = None
    xml_file: Path = Path("enwikiquote-20250601-pages-articles.xml")

    quote_min_length: int = 15
    quote_max_length: int = 800
    quote_min_words: int = 5
    quote_max_words: int = 120
    quote_min_alpha_ratio: float = 0.5

    @property
    def resolved_db_path(self) -> Path:
        return (self.db_path or (self.data_dir / "wikiquote_voice.db")).expanduser()

    @property
    def generated_audio_dir(self) -> Path:
        return (self.data_dir / "api_audio").expanduser()

    @property
    def embeddings_dir(self) -> Path:
        return (self.data_dir / "embeddings").expanduser()


settings = Settings()
