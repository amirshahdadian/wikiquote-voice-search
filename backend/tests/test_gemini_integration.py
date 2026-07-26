import asyncio
from types import SimpleNamespace

import pytest

from backend.app.domain import SearchIntent
from backend.app.integrations.gemini import (
    GeminiService,
    GeminiUnavailable,
    prepare_document,
    prepare_query,
)


class FakeModels:
    async def generate_content(self, **kwargs):
        return SimpleNamespace(
            parsed=SearchIntent(kind="author", search_text="Virginia Woolf", limit=5)
        )

    async def embed_content(self, **kwargs):
        assert kwargs["contents"] == "task: search result | query: courage"
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.0] * 768)])


class FakeClient:
    def __init__(self):
        self.aio = SimpleNamespace(models=FakeModels())


def test_embedding_formats_match_gemini_embedding_2_docs():
    assert prepare_query("courage") == "task: search result | query: courage"
    assert prepare_document("Stay hungry.") == "title: none | text: Stay hungry."


def test_interpret_returns_validated_schema():
    service = GeminiService(
        FakeClient(), "gemini-3.5-flash-lite", "gemini-embedding-2", 768
    )

    intent = asyncio.run(service.interpret("quotes by Virginia Woolf", []))

    assert intent.kind == "author"
    assert intent.search_text == "Virginia Woolf"


def test_missing_client_falls_back_to_topic_intent():
    service = GeminiService(
        None, "gemini-3.5-flash-lite", "gemini-embedding-2", 768
    )

    intent = asyncio.run(service.interpret("hope in difficult times", []))

    assert intent == SearchIntent(
        kind="topic", search_text="hope in difficult times", limit=5
    )


def test_embed_query_requires_exact_dimensions():
    service = GeminiService(
        FakeClient(), "gemini-3.5-flash-lite", "gemini-embedding-2", 768
    )

    vector = asyncio.run(service.embed_query("courage"))

    assert len(vector) == 768


def test_embed_query_without_client_is_explicitly_unavailable():
    service = GeminiService(
        None, "gemini-3.5-flash-lite", "gemini-embedding-2", 768
    )

    with pytest.raises(GeminiUnavailable):
        asyncio.run(service.embed_query("courage"))
