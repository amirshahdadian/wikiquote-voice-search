from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("multipart")

from backend.app import create_app


class StubQuoteSearch:
    async def search_text(self, query: str, limit: int = 5):
        return [
            {
                "quote_id": "quote-1",
                "quote_text": f"Quote about {query}",
                "author_name": "Test Author",
                "source_title": "Test Source",
                "page_title": "Test Author",
                "citation": None,
            }
        ][:limit]

    def autocomplete(self, query: str, limit: int = 5):
        return []


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

    def synthesize_audio(self, text: str, user_id: str | None = None, preferences=None):
        return None, []


class StubConversation:
    async def process_chat_query(self, message: str, conversation_id: str | None = None, selected_user_id: str | None = None):
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
        self.search = StubQuoteSearch()
        self.users = StubUsers()
        self.voice = StubVoice()
        self.conversation = StubConversation()

    def health_flags(self):
        return self.voice.health_flags(search_ready=True)

    def close(self):
        return None


def test_public_route_table_is_stable():
    paths = create_app(container=StubContainer()).openapi()["paths"]
    routes = {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
        if path.startswith("/api/")
    }

    assert routes == {
        ("DELETE", "/api/users/{user_id}"),
        ("GET", "/api/audio/{audio_id}"),
        ("GET", "/api/health"),
        ("GET", "/api/quotes/autocomplete"),
        ("GET", "/api/quotes/search"),
        ("GET", "/api/users"),
        ("GET", "/api/users/{user_id}"),
        ("POST", "/api/chat/query"),
        ("POST", "/api/tts/preview"),
        ("POST", "/api/users/register"),
        ("POST", "/api/users/{user_id}/re-enroll"),
        ("POST", "/api/voice/query"),
    }


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


def test_chat_endpoint_accepts_public_quote_field_names():
    container = StubContainer()

    async def process_chat_query(**_kwargs):
        return {
            "conversation_id": "stub-conversation",
            "recognized_user": None,
            "intent_type": "topic",
            "response_text": "A quotation",
            "best_quote": {
                "quote_id": "quote-1",
                "quote_text": "A sufficiently long quotation.",
                "author_name": "Test Author",
                "source_title": "Test Source",
                "citation": None,
                "page_title": "Test Author",
                "relevance_score": 0.9,
                "search_type": "lexical",
            },
            "related_quotes": [],
            "audio_url": None,
            "warnings": [],
        }

    container.conversation.process_chat_query = process_chat_query
    with TestClient(create_app(container=container)) as client:
        response = client.post("/api/chat/query", json={"message": "courage"})

    assert response.status_code == 200
    assert response.json()["best_quote"]["relevance_score"] == 0.9
