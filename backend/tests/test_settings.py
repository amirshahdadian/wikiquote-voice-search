import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_gemini_defaults_are_stable_and_small():
    app_settings = Settings(_env_file=None)

    assert app_settings.gemini_llm_model == "gemini-3.5-flash-lite"
    assert app_settings.gemini_embedding_model == "gemini-embedding-2"
    assert app_settings.gemini_embedding_dimensions == 768
    assert app_settings.gemini_timeout_seconds == 15.0


def test_api_key_is_optional_for_lexical_only_startup():
    app_settings = Settings(_env_file=None)

    assert app_settings.gemini_api_key is None


def test_embedding_dimensions_match_the_fixed_neo4j_index():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_embedding_dimensions=512)


def test_embedding_dimensions_accept_the_string_read_from_environment(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_EMBEDDING_DIMENSIONS", "768")

    assert Settings(_env_file=None).gemini_embedding_dimensions == 768


def test_gemini_timeout_cannot_be_shorter_than_the_api_minimum():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_timeout_seconds=8)
