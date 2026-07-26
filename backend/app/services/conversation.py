"""Text and voice adapter for the query workflow."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from backend.app.domain import QuoteHit


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
        state = await self._query(message, resolved_id)
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

        state = await self._query(transcript, resolved_id)
        response = await self._response(
            state, resolved_id, selected_user_id, recognized_user, warnings
        )
        response["transcript"] = transcript
        return response

    async def _query(self, message: str, conversation_id: str) -> dict[str, Any]:
        return await self.workflow.run(message, conversation_id)

    async def _response(
        self,
        state: dict[str, Any],
        conversation_id: str,
        selected_user_id: str | None,
        recognized_user: dict[str, Any] | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        hits = [self._as_hit(hit) for hit in state.get("hits", [])]
        index = min(state.get("result_index", 0), max(len(hits) - 1, 0))
        best = hits[index] if hits else None
        related = [
            hit.model_dump(by_alias=True)
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
            "best_quote": best.model_dump(by_alias=True) if best else None,
            "related_quotes": related,
            "audio_url": audio_url,
            "warnings": self._dedupe([*state.get("warnings", []), *warnings]),
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

    @staticmethod
    def _as_hit(value: QuoteHit | dict[str, Any]) -> QuoteHit:
        return value if isinstance(value, QuoteHit) else QuoteHit.model_validate(value)

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))
