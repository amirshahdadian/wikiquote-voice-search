import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_gemini_defaults_are_stable_and_small():
    app_settings = Settings(_env_file=None)

    assert app_settings.gemini_llm_model == "gemini-3.5-flash-lite"
    assert app_settings.gemini_timeout_seconds == 15.0


def test_api_key_is_optional_for_unrewritten_startup():
    app_settings = Settings(_env_file=None)

    assert app_settings.gemini_api_key is None


def test_no_embedding_settings_remain():
    fields = set(Settings.model_fields)

    assert not {name for name in fields if "embedding" in name}


def test_gemini_timeout_cannot_be_shorter_than_the_api_minimum():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_timeout_seconds=8)
