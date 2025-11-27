import os
from pathlib import Path
from typing import Optional, Union

from dotenv import load_dotenv

# Load environment variables from .env file first
load_dotenv()


def get_env_var(key: str, default: Optional[str] = None) -> str:
    """Return the requested environment variable or a provided default."""

    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Environment variable {key} is required but not set")
    return value


def _get_path_var(key: str, default: Union[Path, str]) -> Path:
    """Return an environment variable coerced to :class:`Path`."""

    raw_value = os.getenv(key)
    if raw_value:
        return Path(raw_value).expanduser()
    if isinstance(default, Path):
        return default.expanduser()
    return Path(default).expanduser()


def _get_int_var(key: str, default: Optional[int] = None) -> Optional[int]:
    """Return an optional integer environment variable."""

    raw_value = os.getenv(key)
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


class Config:
    """Configuration class for the Wikiquote Voice Search application."""

    # Neo4j Configuration
    NEO4J_URI: str = get_env_var("NEO4J_URI", "neo4j://127.0.0.1:7687")
    NEO4J_USERNAME: str = get_env_var("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD: str = get_env_var("NEO4J_PASSWORD")

    # Application Settings
    BATCH_SIZE: int = int(get_env_var("BATCH_SIZE", "1000"))
    SEARCH_LIMIT: int = int(get_env_var("SEARCH_LIMIT", "5"))
    LOG_LEVEL: str = get_env_var("LOG_LEVEL", "INFO")
    PARSE_PAGE_LIMIT: Optional[int] = _get_int_var("PARSE_PAGE_LIMIT")

    # File system locations
    DATA_DIR: Path = _get_path_var("DATA_DIR", Path("data"))
    ARTIFACTS_DIR: Path = _get_path_var("ARTIFACTS_DIR", Path("artifacts"))
    MODELS_DIR: Path = _get_path_var("MODELS_DIR", Path("models"))
    RECORDINGS_DIR: Path = _get_path_var("RECORDINGS_DIR", DATA_DIR / "recordings")
    DB_PATH: Path = _get_path_var("DB_PATH", DATA_DIR / "wikiquote_voice.db")
    QUOTES_FILE: Path = _get_path_var("QUOTES_FILE", DATA_DIR / "extracted_quotes.json")
    XML_FILE: Path = _get_path_var("XML_FILE", Path("enwikiquote-20250601-pages-articles.xml"))
