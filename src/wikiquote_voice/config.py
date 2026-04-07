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

    # NeMo 2.x model configuration
    NEMO_TTS_SPEC_MODEL: str = get_env_var("NEMO_TTS_SPEC_MODEL", "tts_en_fastpitch")
    NEMO_TTS_VOCODER_MODEL: str = get_env_var("NEMO_TTS_VOCODER_MODEL", "tts_en_hifigan")
    NEMO_SPEAKER_MODEL: str = get_env_var("NEMO_SPEAKER_MODEL", "titanet_large")
    NEMO_ASR_MODEL: str = get_env_var("NEMO_ASR_MODEL", "stt_en_conformer_ctc_small")
    NEMO_ASR_MULTILINGUAL_MODEL: str = get_env_var("NEMO_ASR_MULTILINGUAL_MODEL", "")

    # Parser Configuration - Quote Validation
    QUOTE_MIN_LENGTH: int = int(get_env_var("QUOTE_MIN_LENGTH", "15"))
    QUOTE_MAX_LENGTH: int = int(get_env_var("QUOTE_MAX_LENGTH", "500"))
    QUOTE_MIN_WORDS: int = int(get_env_var("QUOTE_MIN_WORDS", "5"))
    QUOTE_MAX_WORDS: int = int(get_env_var("QUOTE_MAX_WORDS", "120"))
    QUOTE_MAX_SENTENCES: int = int(get_env_var("QUOTE_MAX_SENTENCES", "6"))
    QUOTE_MIN_ALPHA_RATIO: float = float(get_env_var("QUOTE_MIN_ALPHA_RATIO", "0.5"))
