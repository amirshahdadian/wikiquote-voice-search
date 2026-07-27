from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from typing import Any

from backend.models import QueryState, QuoteHit, SearchIntent


# Quote Search

class QuoteSearch:
    """Send each typed intent to one fixed Neo4j query."""

    def __init__(self, repository: Any):
        self.repository = repository

    async def search_text(self, query: str, limit: int = 5) -> list[QuoteHit]:
        return await self.search(
            SearchIntent(kind="topic", search_text=query, limit=limit)
        )

    def autocomplete(self, query: str, limit: int = 5) -> list[QuoteHit]:
        return self.repository.fragment_search(query, limit)

    async def search(self, intent: SearchIntent) -> list[QuoteHit]:
        if intent.kind == "author":
            return await asyncio.to_thread(
                self.repository.author_search,
                intent.search_text or intent.author,
                intent.limit,
            )
        if intent.kind == "random":
            item = await asyncio.to_thread(self.repository.random_quote)
            return [item] if item else []
        if intent.kind == "quote_fragment":
            exact = await asyncio.to_thread(
                self.repository.fragment_search,
                intent.search_text,
                intent.limit,
            )
            if exact:
                return exact
            return await asyncio.to_thread(
                self.repository.lexical_search,
                intent.search_text,
                intent.limit,
            )
        if intent.author.strip():
            narrowed = await asyncio.to_thread(
                self.repository.author_topic_search,
                intent.search_text,
                intent.author,
                intent.limit,
            )
            if narrowed:
                return narrowed
        return await asyncio.to_thread(
            self.repository.lexical_search, intent.search_text, intent.limit
        )


# Query Workflow

class QueryWorkflow:
    def __init__(self, gemini: Any, search: Any, max_threads: int = 1000):
        self.gemini = gemini
        self.search = search
        self.max_threads = max_threads
        self.states: OrderedDict[str, QueryState] = OrderedDict()

    async def run(self, message: str, conversation_id: str) -> QueryState:
        previous = self.states.pop(conversation_id, {})
        intent = await self.gemini.interpret(message, previous.get("history", []))
        hits = previous.get("hits", [])
        result_index = previous.get("result_index", 0)
        warnings: list[str] = []

        if intent.kind == "alternative" and hits:
            if result_index + 1 < len(hits):
                result_index += 1
            else:
                warnings.append("no_additional_matches")
        elif intent.kind not in {"repeat", "attribution"} or not hits:
            hits = await self.search.search(intent)
            result_index = 0
            if not hits:
                warnings.append("no_quote_found")

        if hits:
            selected = hits[min(result_index, len(hits) - 1)]
            author = selected.author_name or "Unknown attribution"
            if intent.kind == "attribution":
                response_text = (
                    f"That quotation is attributed to {author} "
                    f"on {selected.page_title}."
                )
            else:
                response_text = f'"{selected.quote_text}" — {author}'
        else:
            response_text = f'I could not find a reliable match for "{message}".'

        state: QueryState = {
            "intent": intent,
            "hits": hits,
            "result_index": result_index,
            "response_text": response_text,
            "warnings": warnings,
            "history": [
                *previous.get("history", []),
                {"role": "user", "content": message},
                {"role": "assistant", "content": response_text},
            ][-8:],
        }
        self.states[conversation_id] = state
        while len(self.states) > self.max_threads:
            self.states.popitem(last=False)
        return state

# Conversation

class ConversationService:
    def __init__(self, workflow: Any, user_service: Any, voice_service: Any):
        self.workflow = workflow
        self.user_service = user_service
        self.voice_service = voice_service

    async def process_chat_query(
        self,
        message: str,
        conversation_id: str | None = None,
        selected_user_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_id = conversation_id or uuid.uuid4().hex
        recognized_user, warnings = self._selected_user(selected_user_id)
        state = await self.workflow.run(message, resolved_id)
        return await self._response(
            state, resolved_id, selected_user_id, recognized_user, warnings
        )

    async def process_voice_query(
        self,
        audio_bytes: bytes,
        filename: str,
        conversation_id: str | None = None,
        selected_user_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_id = conversation_id or uuid.uuid4().hex
        transcript = await asyncio.to_thread(
            self.voice_service.transcribe_bytes, audio_bytes, filename
        )
        if not transcript:
            return {
                "conversation_id": resolved_id,
                "transcript": "",
                "recognized_user": None,
                "intent_type": "asr_error",
                "response_text": "I’m not sure I understood. Please repeat your request.",
                "best_quote": None,
                "related_quotes": [],
                "audio_url": None,
                "warnings": ["low_asr_confidence"],
            }

        recognized_user, warnings = self._selected_user(selected_user_id)
        if not selected_user_id:
            matched_user, confidence = await asyncio.to_thread(
                self.voice_service.identify_speaker, audio_bytes, filename
            )
            if matched_user:
                recognized_user = self.user_service.load_recognized_user(
                    matched_user, confidence, "speaker_id"
                )
            else:
                warnings.append("speaker_not_recognized")

        state = await self.workflow.run(transcript, resolved_id)
        response = await self._response(
            state, resolved_id, selected_user_id, recognized_user, warnings
        )
        response["transcript"] = transcript
        return response

    async def _response(
        self,
        state: dict[str, Any],
        conversation_id: str,
        selected_user_id: str | None,
        recognized_user: dict[str, Any] | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        hits: list[QuoteHit] = state.get("hits", [])
        index = min(state.get("result_index", 0), max(len(hits) - 1, 0))
        best = hits[index] if hits else None
        related = [
            hit.model_dump()
            for hit_index, hit in enumerate(hits)
            if hit_index != index
        ][:3]

        audio_url = None
        response_text = state.get("response_text", "")
        if response_text:
            user_id = selected_user_id or (
                recognized_user["user_id"] if recognized_user else None
            )
            audio_url, tts_warnings = await asyncio.to_thread(
                self.voice_service.synthesize_audio, response_text, user_id
            )
            warnings.extend(tts_warnings)

        intent = state.get("intent")
        return {
            "conversation_id": conversation_id,
            "recognized_user": recognized_user,
            "intent_type": intent.kind if intent else "topic",
            "response_text": response_text,
            "best_quote": best.model_dump() if best else None,
            "related_quotes": related,
            "audio_url": audio_url,
            "warnings": list(dict.fromkeys([*state.get("warnings", []), *warnings])),
        }

    def _selected_user(
        self, user_id: str | None
    ) -> tuple[dict[str, Any] | None, list[str]]:
        if not user_id:
            return None, []
        if self.user_service.get_user(user_id) is None:
            return None, ["selected_user_not_found"]
        return (
            self.user_service.load_recognized_user(user_id, 1.0, "selected"),
            [],
        )
