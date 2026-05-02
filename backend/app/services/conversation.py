"""Conversation and query orchestration service."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid

from backend.app.services.quote_search import QuoteSearchService
from backend.app.services.users import UserService
from backend.app.services.voice import VoiceService


@dataclass(slots=True)
class ConversationState:
    conversation_id: str
    history: list[dict[str, str]] = field(default_factory=list)
    last_query: str | None = None
    last_results: list[dict[str, Any]] = field(default_factory=list)
    last_response_text: str | None = None
    last_intent_type: str | None = None
    last_result_index: int = 0


class IntentParser:
    """Focused rule-based intent parser."""

    def extract_intent(self, message: str) -> dict[str, Any]:
        import re

        message_lower = message.lower().strip()
        quote_lookup_match = re.search(r"who (?:said|wrote)\s+(.+)", message_lower)
        if quote_lookup_match:
            quote_fragment = re.sub(r"[?.!,;]+$", "", quote_lookup_match.group(1).strip()).strip()
            if quote_fragment:
                return {"type": "topic_search", "query": quote_fragment, "limit": 5}

        topic_patterns = [
            r"(?:something|anything|quotes?)\s+(?:about|on|regarding)\s+(.+)",
            r"(?:find|search|show|get|give me|looking for|want|need)\s+(?:some\s+)?quotes?\s+(?:about|on|regarding)\s+(.+)",
            r"(?:please\s+)?(?:find|get|show)\s+(?:me\s+)?(?:some\s+)?quotes?\s+(?:about|on|regarding)\s+(.+)",
            r"quotes?\s+(?:about|on|regarding)\s+(.+)",
            r"(?:what are|tell me)\s+(?:some\s+)?quotes?\s+(?:about|on|regarding)\s+(.+)",
            r"^(?:about|on)\s+(.+)",
        ]
        for pattern in topic_patterns:
            match = re.search(pattern, message_lower)
            if match:
                topic = re.sub(r"\b(quotes?|please)\b", "", re.sub(r"[?.!,;]+$", "", match.group(1).strip())).strip()
                if topic and len(topic) > 1:
                    return {"type": "topic_search", "query": topic, "limit": 5}

        if "about" not in message_lower and "regarding" not in message_lower:
            author_patterns = [
                r"what\s+(?:did|has|have)\s+(.+?)\s+(?:say|said|write|written|wrote)",
                r"(?:show me|find|get)\s+(.+?)(?:'s)?\s+quotes?",
                r"(.+?)(?:'s)?\s+quotes?$",
                r"quotes?\s+(?:by|from)\s+(.+)",
            ]
            for pattern in author_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    author_name = re.sub(r"\b(quotes?|the|some|me)\b", "", match.group(1).strip()).strip()
                    if author_name and len(author_name) > 2 and not any(word in author_name for word in ["about", "on", "regarding"]):
                        return {"type": "author_search", "author": author_name.title(), "limit": 5}

        return {"type": "topic_search", "query": message, "limit": 5}


class ConversationService:
    """Orchestrate text and voice interactions."""

    def __init__(
        self,
        quote_search: QuoteSearchService,
        user_service: UserService,
        voice_service: VoiceService,
        conversation_history_limit: int,
    ):
        self.quote_search = quote_search
        self.user_service = user_service
        self.voice_service = voice_service
        self.intent_parser = IntentParser()
        self.conversation_history_limit = conversation_history_limit
        self.conversations: dict[str, ConversationState] = {}

    def process_chat_query(
        self,
        message: str,
        conversation_id: str | None = None,
        selected_user_id: str | None = None,
    ) -> dict[str, Any]:
        conversation = self._get_or_create_conversation(conversation_id)
        recognized_user = None
        warnings: list[str] = []
        if selected_user_id:
            profile = self.user_service.get_user(selected_user_id)
            if profile is None:
                warnings.append("selected_user_not_found")
            else:
                recognized_user = self.user_service.load_recognized_user(selected_user_id, 1.0, "selected")

        response = self._build_query_response(message, conversation, selected_user_id, recognized_user, warnings)
        response["conversation_id"] = conversation.conversation_id
        response["recognized_user"] = recognized_user
        return response

    def process_voice_query(
        self,
        audio_bytes: bytes,
        filename: str,
        conversation_id: str | None = None,
        selected_user_id: str | None = None,
    ) -> dict[str, Any]:
        conversation = self._get_or_create_conversation(conversation_id)
        transcript, normalized_transcript = self.voice_service.transcribe_bytes(audio_bytes, filename)
        if not transcript:
            return {
                "conversation_id": conversation.conversation_id,
                "transcript": "",
                "normalized_transcript": "",
                "recognized_user": None,
                "intent_type": "asr_error",
                "response_text": "I’m not sure I understood. Please repeat your request.",
                "best_quote": None,
                "related_quotes": [],
                "audio_url": None,
                "warnings": ["low_asr_confidence"],
            }

        recognized_user = None
        warnings: list[str] = []
        if selected_user_id:
            profile = self.user_service.get_user(selected_user_id)
            if profile is None:
                warnings.append("selected_user_not_found")
            else:
                recognized_user = self.user_service.load_recognized_user(selected_user_id, 1.0, "selected")
        else:
            matched_user, confidence = self.voice_service.identify_speaker(audio_bytes, filename)
            if matched_user:
                recognized_user = self.user_service.load_recognized_user(matched_user, confidence, "speaker_id")
            else:
                warnings.append("speaker_not_recognized")

        response = self._build_query_response(
            transcript,
            conversation,
            selected_user_id,
            recognized_user,
            warnings,
        )
        response.update(
            {
                "conversation_id": conversation.conversation_id,
                "transcript": transcript,
                "normalized_transcript": normalized_transcript,
                "recognized_user": recognized_user,
            }
        )
        return response

    def _build_query_response(
        self,
        message: str,
        conversation: ConversationState,
        selected_user_id: str | None,
        recognized_user: dict[str, Any] | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        working_warnings = list(warnings)
        query_response = self._run_query_logic(message, conversation, working_warnings)
        audio_url = None
        if query_response["response_text"]:
            preference_source = selected_user_id or (recognized_user["user_id"] if recognized_user else None)
            audio_url, tts_warnings = self.voice_service.synthesize_audio(
                text=query_response["response_text"],
                user_id=preference_source,
            )
            working_warnings.extend(tts_warnings)
        query_response["audio_url"] = audio_url
        query_response["warnings"] = self._dedupe_preserve_order(working_warnings)
        return query_response

    def _run_query_logic(
        self,
        message: str,
        conversation: ConversationState,
        warnings: list[str],
    ) -> dict[str, Any]:
        follow_up = self._handle_follow_up(message, conversation, warnings)
        if follow_up is not None:
            return follow_up

        intent = self.intent_parser.extract_intent(message)
        original_lower = message.lower().strip()
        intent_type = "quote_lookup" if original_lower.startswith(("who said ", "who wrote ")) else intent["type"]

        if intent["type"] == "author_search":
            results = self.quote_search.search_by_author(intent["author"], limit=intent["limit"])
            query_label = intent["author"]
        else:
            results = self.quote_search.search_quotes(intent["query"], limit=max(intent["limit"], 5))
            query_label = intent["query"]

        if not results:
            response_text = f"I could not find an exact match for '{query_label}'. Please try again or rephrase."
            warnings.append("no_quote_found")
            self._record_conversation(conversation, message, response_text, [], intent_type)
            return {
                "intent_type": intent_type,
                "response_text": response_text,
                "best_quote": None,
                "related_quotes": [],
            }

        if len(results) > 1:
            warnings.append("multiple_close_matches")

        best_quote = dict(results[0])
        related_quotes = [dict(result) for result in results[1:4]]
        response_text = self._format_primary_response(intent_type, query_label, best_quote)
        self._record_conversation(conversation, message, response_text, [dict(result) for result in results], intent_type)
        return {
            "intent_type": intent_type,
            "response_text": response_text,
            "best_quote": best_quote,
            "related_quotes": related_quotes,
        }

    def _handle_follow_up(
        self,
        message: str,
        conversation: ConversationState,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        lowered = message.lower().strip()
        if not conversation.last_results:
            return None
        if any(phrase in lowered for phrase in ("read it again", "say it again", "repeat", "read that again")):
            best_quote = dict(conversation.last_results[conversation.last_result_index])
            return {
                "intent_type": "repeat",
                "response_text": conversation.last_response_text or self._format_primary_response(
                    conversation.last_intent_type or "topic_search",
                    conversation.last_query or "that",
                    best_quote,
                ),
                "best_quote": best_quote,
                "related_quotes": [dict(result) for result in conversation.last_results[1:4]],
            }
        if any(phrase in lowered for phrase in ("who wrote that", "who said that", "who wrote it", "who said it")):
            best_quote = dict(conversation.last_results[conversation.last_result_index])
            response_text = (
                f'That quote is by {best_quote["author_name"]} from {best_quote["source_title"]}. '
                f'The quote is "{best_quote["quote_text"]}".'
            )
            conversation.last_response_text = response_text
            return {
                "intent_type": "follow_up_attribution",
                "response_text": response_text,
                "best_quote": best_quote,
                "related_quotes": [dict(result) for result in conversation.last_results[1:4]],
            }
        if any(phrase in lowered for phrase in ("another", "another one", "give me another", "give me another one")):
            next_index = conversation.last_result_index + 1
            if next_index >= len(conversation.last_results):
                warnings.append("no_additional_matches")
                return {
                    "intent_type": "follow_up_alternative",
                    "response_text": "I don’t have another close match from the previous search. Please ask a new question.",
                    "best_quote": dict(conversation.last_results[conversation.last_result_index]),
                    "related_quotes": [],
                }
            conversation.last_result_index = next_index
            best_quote = dict(conversation.last_results[next_index])
            conversation.last_response_text = self._format_primary_response(
                "follow_up_alternative",
                conversation.last_query or "that topic",
                best_quote,
            )
            return {
                "intent_type": "follow_up_alternative",
                "response_text": conversation.last_response_text,
                "best_quote": best_quote,
                "related_quotes": [
                    dict(result)
                    for idx, result in enumerate(conversation.last_results)
                    if idx != next_index
                ][:3],
            }
        return None

    @staticmethod
    def _format_primary_response(intent_type: str, query_label: str, quote: dict[str, Any]) -> str:
        quote_text = quote["quote_text"]
        author = quote["author_name"]
        source = quote["source_title"]
        if intent_type == "author_search":
            return f'Here is a quote by {author}: "{quote_text}" from {source}.'
        if intent_type == "quote_lookup":
            return f'The best matching quote is "{quote_text}" by {author} from {source}.'
        if intent_type == "follow_up_alternative":
            return f'Here is another quote: "{quote_text}" by {author} from {source}.'
        return f'"{quote_text}" by {author} from {source}.'

    def _get_or_create_conversation(self, conversation_id: str | None) -> ConversationState:
        if conversation_id and conversation_id in self.conversations:
            return self.conversations[conversation_id]
        resolved_id = conversation_id or uuid.uuid4().hex
        conversation = ConversationState(conversation_id=resolved_id)
        self.conversations[resolved_id] = conversation
        return conversation

    def _record_conversation(
        self,
        conversation: ConversationState,
        user_message: str,
        response_text: str,
        results: list[dict[str, Any]],
        intent_type: str,
    ) -> None:
        conversation.history.append({"role": "user", "content": user_message})
        conversation.history.append({"role": "assistant", "content": response_text})
        conversation.history = conversation.history[-(self.conversation_history_limit * 2) :]
        conversation.last_query = user_message
        conversation.last_results = results
        conversation.last_response_text = response_text
        conversation.last_intent_type = intent_type
        conversation.last_result_index = 0

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

