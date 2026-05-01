from __future__ import annotations

from backend.app.core.settings import Settings


def test_frontend_origins_accepts_json_array(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", '["https://example.com","http://localhost:3000"]')

    settings = Settings(_env_file=None)

    assert settings.frontend_origins == ["https://example.com", "http://localhost:3000"]


def test_frontend_origins_accepts_comma_separated_values(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://example.com, http://localhost:3000")

    settings = Settings(_env_file=None)

    assert settings.frontend_origins == ["https://example.com", "http://localhost:3000"]
