"""Application settings loaded from environment and .env files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Canonical runtime settings for the FastAPI backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_prefix: str = "/api"
    frontend_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    conversation_history_limit: int = 8

    neo4j_uri: str = "neo4j://127.0.0.1:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str | None = None

    batch_size: int = 1000
    search_limit: int = 5
    log_level: str = "INFO"
    parse_page_limit: int | None = None

    asr_backend: str = "mlx"
    asr_model_name: str | None = None
    asr_device: str = "auto"
    asr_compute_type: str | None = None
    asr_beam_size: int = 5

    data_dir: Path = Path("data")
    artifacts_dir: Path = Path("artifacts")
    models_dir: Path = Path("models")
    recordings_dir: Path | None = None
    db_path: Path | None = None
    quotes_file: Path | None = None
    xml_file: Path = Path("enwikiquote-20250601-pages-articles.xml")

    quote_min_length: int = 15
    quote_max_length: int = 500
    quote_min_words: int = 5
    quote_max_words: int = 120
    quote_max_sentences: int = 6
    quote_min_alpha_ratio: float = 0.5

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def _parse_frontend_origins(cls, value: Any) -> Any:
        if value is None or value == "":
            return ["http://localhost:3000", "http://127.0.0.1:3000"]
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("asr_backend")
    @classmethod
    def _validate_asr_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"mlx", "faster"}:
            raise ValueError("ASR_BACKEND must be one of: mlx, faster")
        return normalized

    @property
    def resolved_recordings_dir(self) -> Path:
        return (self.recordings_dir or (self.data_dir / "recordings")).expanduser()

    @property
    def resolved_db_path(self) -> Path:
        return (self.db_path or (self.data_dir / "wikiquote_voice.db")).expanduser()

    @property
    def resolved_quotes_file(self) -> Path:
        return (self.quotes_file or (self.data_dir / "extracted_quotes.json")).expanduser()

    @property
    def generated_audio_dir(self) -> Path:
        return (self.data_dir / "api_audio").expanduser()

    @property
    def embeddings_dir(self) -> Path:
        return (self.data_dir / "embeddings").expanduser()


settings = Settings()
