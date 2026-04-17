from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("multipart")

from backend.app.main import create_app


class StubQuoteSearch:
    def search_quotes(self, query: str, limit: int = 5):
        return [
            {
                "quote_text": f"Quote about {query}",
                "author_name": "Test Author",
                "source_title": "Test Source",
            }
        ][:limit]

    def get_random_quote(self):
        return {
            "quote_text": "Random quote",
            "author_name": "Test Author",
            "source_title": "Test Source",
        }

    def search_by_theme(self, theme: str, limit: int = 10):
        return self.search_quotes(theme, limit)

    def autocomplete(self, query: str, limit: int = 5):
        return self.search_quotes(query, limit)

    def intelligent_search(self, query: str, limit: int = 10):
        return self.search_quotes(query, limit)

    def voice_search(self, query: str, limit: int = 3):
        return self.search_quotes(query, limit)

    def get_popular_authors(self, limit: int = 20):
        return [{"author_name": "Test Author", "quote_count": 1}]

    def close(self):
        return None


class StubUsers:
    def list_users(self):
        return []

    def get_user(self, user_id: str):
        return None


class StubVoice:
    def health_flags(self, search_ready: bool):
        return {
            "search": search_ready,
            "asr": True,
            "speaker_id": True,
            "tts": True,
            "sqlite": True,
        }

    def resolve_audio_path(self, audio_id: str):
        return None

    def create_tts_preview(self, text: str, user_id: str | None = None, preferences=None):
        return {"audio_url": None, "warnings": []}


class StubConversation:
    def process_chat_query(self, message: str, conversation_id: str | None = None, selected_user_id: str | None = None):
        return {
            "conversation_id": conversation_id or "stub-conversation",
            "recognized_user": None,
            "intent_type": "topic_search",
            "response_text": f"Echo: {message}",
            "best_quote": None,
            "related_quotes": [],
            "audio_url": None,
            "warnings": [],
        }


class StubContainer:
    def __init__(self):
        self.quote_search = StubQuoteSearch()
        self.users = StubUsers()
        self.voice = StubVoice()
        self.conversation = StubConversation()

    def health_flags(self):
        return self.voice.health_flags(search_ready=True)

    def close(self):
        return None


def test_health_endpoint():
    with TestClient(create_app(container=StubContainer())) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["search"] is True


def test_chat_endpoint():
    with TestClient(create_app(container=StubContainer())) as client:
        response = client.post("/api/chat/query", json={"message": "find a quote about courage"})
    assert response.status_code == 200
    assert response.json()["intent_type"] == "topic_search"
