from backend.app.core.settings import Settings


def test_gemini_defaults_are_stable_and_small():
    app_settings = Settings(_env_file=None)

    assert app_settings.gemini_llm_model == "gemini-3.5-flash-lite"
    assert app_settings.gemini_embedding_model == "gemini-embedding-2"
    assert app_settings.gemini_embedding_dimensions == 768
    assert app_settings.gemini_timeout_seconds == 8.0


def test_api_key_is_optional_for_lexical_only_startup():
    app_settings = Settings(_env_file=None)

    assert app_settings.gemini_api_key is None
