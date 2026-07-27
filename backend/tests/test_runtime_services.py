from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app import AppContainer
from backend.models import QuoteHit, SearchIntent
from backend.config import Settings
from backend.search import ConversationService
from backend.voice import VoiceService


HIT = QuoteHit(
    quote_id="quote-1",
    quote_text="Simplicity is prerequisite for reliability.",
    author_name="Edsger Dijkstra",
    source_title=None,
    citation="EWD 498",
    page_title="Edsger W. Dijkstra",
    relevance_score=0.91,
    search_type="lexical",
)


def test_quote_hit_uses_public_api_field_names_when_serialized():
    assert HIT.model_dump(by_alias=True) == {
        "quote_id": "quote-1",
        "quote_text": "Simplicity is prerequisite for reliability.",
        "author_name": "Edsger Dijkstra",
        "source_title": None,
        "citation": "EWD 498",
        "page_title": "Edsger W. Dijkstra",
        "relevance_score": 0.91,
        "search_type": "lexical",
    }


class FakeWorkflow:
    def __init__(self):
        self.message = None
        self.conversation_id = None

    async def run(self, message, conversation_id):
        self.message = message
        self.conversation_id = conversation_id
        return {
            "message": message,
            "conversation_id": conversation_id,
            "intent": SearchIntent(
                kind="topic", search_text=message, limit=5
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

    assert workflow.message == "a quote about simplicity"
    assert workflow.conversation_id == "conversation-1"
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


def test_health_reports_unreachable_neo4j_as_not_ready():
    class HealthVoice:
        def health_flags(self, search_ready):
            return {"search": search_ready}

    container = object.__new__(AppContainer)
    container.repository = SimpleNamespace(is_ready=lambda: False)
    container.voice = HealthVoice()

    assert container.health_flags()["search"] is False
