from __future__ import annotations

import pytest

from backend.app.domain import QuoteHit, SearchIntent
from backend.app.core.settings import Settings
from backend.app.services.conversation import ConversationService
from backend.app.services.quote_search import QuoteSearchService
from backend.app.services.voice import VoiceService


HIT = QuoteHit(
    quote_id="quote-1",
    quote_text="Simplicity is prerequisite for reliability.",
    author_name="Edsger Dijkstra",
    work_title=None,
    citation="EWD 498",
    page_title="Edsger W. Dijkstra",
    score=0.91,
    search_type="hybrid",
)


class FakeSearch:
    def __init__(self):
        self.intent = None

    async def search(self, intent):
        self.intent = intent
        return [HIT]


class FakeRepository:
    driver = object()

    def autocomplete(self, text, limit):
        return [HIT]

    def random_quote(self):
        return HIT

    def popular_authors(self, limit):
        return [{"author_name": "Edsger Dijkstra", "quote_count": 1}]

    def close(self):
        pass


@pytest.mark.asyncio
async def test_quote_service_uses_hybrid_search_and_serializes_provenance():
    hybrid = FakeSearch()
    service = QuoteSearchService(FakeRepository(), hybrid)

    results = await service.search_quotes("software simplicity", limit=3)

    assert hybrid.intent == SearchIntent(
        kind="topic", search_text="software simplicity", limit=3
    )
    assert results == [
        {
            "quote_id": "quote-1",
            "quote_text": "Simplicity is prerequisite for reliability.",
            "author_name": "Edsger Dijkstra",
            "source_title": None,
            "page_title": "Edsger W. Dijkstra",
            "citation": "EWD 498",
            "relevance_score": 0.91,
            "search_type": "hybrid",
        }
    ]


class FakeWorkflow:
    def __init__(self):
        self.input = None
        self.config = None

    async def ainvoke(self, payload, config):
        self.input = payload
        self.config = config
        return {
            **payload,
            "intent": SearchIntent(
                kind="topic", search_text=payload["message"], limit=5
            ),
            "hits": [HIT],
            "result_index": 0,
            "response_text": '"Simplicity is prerequisite for reliability." — Edsger Dijkstra',
            "warnings": [],
        }


class FakeUsers:
    def get_user(self, user_id):
        if user_id == "known":
            return {"user_id": "known"}
        return None

    def load_recognized_user(self, user_id, confidence, source):
        return {
            "user_id": user_id,
            "display_name": "Known User",
            "confidence": confidence,
            "source": source,
        }


class FakeVoice:
    def synthesize_audio(self, text, user_id=None):
        return ("/api/audio/test.wav", [])


@pytest.mark.asyncio
async def test_conversation_service_invokes_one_workflow_thread():
    workflow = FakeWorkflow()
    service = ConversationService(workflow, FakeUsers(), FakeVoice())

    result = await service.process_chat_query(
        "a quote about simplicity",
        conversation_id="conversation-1",
        selected_user_id="known",
    )

    assert workflow.input == {
        "message": "a quote about simplicity",
        "conversation_id": "conversation-1",
    }
    assert workflow.config == {
        "configurable": {"thread_id": "conversation-1"}
    }
    assert result["intent_type"] == "topic"
    assert result["best_quote"]["quote_id"] == "quote-1"
    assert result["best_quote"]["author_name"] == "Edsger Dijkstra"
    assert result["audio_url"] == "/api/audio/test.wav"
    assert result["recognized_user"]["user_id"] == "known"


@pytest.mark.asyncio
async def test_conversation_reports_missing_selected_user_without_failing():
    service = ConversationService(FakeWorkflow(), FakeUsers(), FakeVoice())

    result = await service.process_chat_query(
        "simplicity", selected_user_id="missing"
    )

    assert result["recognized_user"] is None
    assert result["warnings"] == ["selected_user_not_found"]


class BrokenTTS:
    def synthesize_personalized(self, **kwargs):
        raise RuntimeError("model unavailable")


def test_voice_service_reports_kokoro_unavailable_without_network_fallback(
    tmp_path,
):
    service = VoiceService(
        Settings(data_dir=tmp_path),
        tts_service=BrokenTTS(),
    )

    assert service.synthesize_audio("A quotation") == (
        None,
        ["tts_unavailable"],
    )
