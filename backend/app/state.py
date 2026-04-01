"""Shared backend state and domain orchestration for the web API."""
from __future__ import annotations

import importlib.util
import logging
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from services.asr_service import ASRService
from services.chatbot_service import ChatbotService
from services.speaker_identification import SpeakerIdentificationService
from services.tts_service import TTSService
from services.tts_service_simple import SimpleTTSService
from src.wikiquote_voice.config import Config
from src.wikiquote_voice.search.service import QuoteSearchService
from src.wikiquote_voice.storage.sqlite import (
    create_user,
    delete_tts_preferences,
    delete_user_record,
    delete_user_profile,
    get_tts_preferences,
    get_user_profile,
    initialize_database,
    list_tts_preference_users,
    list_user_profiles,
    save_tts_preferences,
    save_user_profile,
)

from .settings import AppSettings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ConversationState:
    conversation_id: str
    history: list[dict[str, str]] = field(default_factory=list)
    last_query: Optional[str] = None
    last_results: list[dict[str, Any]] = field(default_factory=list)
    last_response_text: Optional[str] = None
    last_intent_type: Optional[str] = None
    last_result_index: int = 0


class BackendState:
    """Coordinator for reusable services and API-oriented workflows."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        initialize_database(Config.DB_PATH)
        self.settings.generated_audio_dir.mkdir(parents=True, exist_ok=True)
        self.settings.embeddings_dir.mkdir(parents=True, exist_ok=True)

        self.search_service = QuoteSearchService(
            Config.NEO4J_URI,
            Config.NEO4J_USERNAME,
            Config.NEO4J_PASSWORD,
        )
        self.search_service.connect()
        self.search_service.build_semantic_index(sample_size=10000)

        # We only need the intent extraction logic, not ChatbotService.__init__.
        self.intent_parser = ChatbotService.__new__(ChatbotService)

        self._asr_service: Optional[ASRService] = None
        self._speaker_service: Optional[SpeakerIdentificationService] = None
        self._tts_service: Optional[TTSService] = None
        self._simple_tts_service: Optional[SimpleTTSService] = None
        self.conversations: dict[str, ConversationState] = {}

    def close(self) -> None:
        self.search_service.close()

    def health_flags(self) -> dict[str, bool]:
        return {
            "search": self.search_service.driver is not None,
            "asr": any(
                importlib.util.find_spec(name) is not None
                for name in ("whisper", "transformers")
            ),
            "speaker_id": importlib.util.find_spec("nemo.collections.asr") is not None,
            "tts": (
                importlib.util.find_spec("nemo.collections.tts") is not None
                or importlib.util.find_spec("gtts") is not None
            ),
            "sqlite": Path(Config.DB_PATH).exists(),
        }

    def get_asr_service(self) -> ASRService:
        if self._asr_service is None:
            self._asr_service = ASRService(model_name="small", backend="auto")
        return self._asr_service

    def get_speaker_service(self) -> SpeakerIdentificationService:
        if self._speaker_service is None:
            self._speaker_service = SpeakerIdentificationService(threshold=0.5)
        return self._speaker_service

    def get_tts_service(self) -> TTSService:
        if self._tts_service is None:
            self._tts_service = TTSService(device="cpu", db_path=str(Config.DB_PATH))
        return self._tts_service

    def get_simple_tts_service(self) -> SimpleTTSService:
        if self._simple_tts_service is None:
            self._simple_tts_service = SimpleTTSService(device="cpu", db_path=str(Config.DB_PATH))
        return self._simple_tts_service

    def list_users(self) -> list[dict[str, Any]]:
        known_ids = self._all_known_user_ids()
        users = [self._compose_user_profile(user_id) for user_id in known_ids]
        return sorted(users, key=lambda item: item["display_name"].lower())

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        if user_id not in self._all_known_user_ids():
            return None
        return self._compose_user_profile(user_id)

    def register_user(
        self,
        display_name: str,
        group_identifier: Optional[str],
        preferences: dict[str, Any],
        audio_samples: list[tuple[str, bytes]],
    ) -> dict[str, Any]:
        user_id = self._slugify_user_id(display_name)
        if not user_id:
            raise ValueError("Display name must contain letters or numbers")
        if user_id in self._all_known_user_ids():
            raise ValueError(f"User '{user_id}' already exists")
        if len(audio_samples) < 3:
            raise ValueError("At least 3 audio samples are required")

        sample_paths = self._materialize_uploads(audio_samples)
        try:
            embedding = self.get_speaker_service().enroll_speaker(user_id, sample_paths)
            self.get_speaker_service().save_embedding(
                embedding,
                str(self.settings.embeddings_dir / f"{user_id}.pkl"),
            )
            create_user(user_id, Config.DB_PATH)
            save_user_profile(user_id, display_name, group_identifier, Config.DB_PATH)
            save_tts_preferences(user_id, preferences, Config.DB_PATH)
            return self._compose_user_profile(user_id)
        finally:
            self._cleanup_paths(sample_paths)

    def update_user_preferences(self, user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        profile = self.get_user(user_id)
        if profile is None:
            raise KeyError(f"Unknown user '{user_id}'")

        save_tts_preferences(user_id, preferences, Config.DB_PATH)
        return self._compose_user_profile(user_id)

    def re_enroll_user(
        self,
        user_id: str,
        audio_samples: list[tuple[str, bytes]],
    ) -> dict[str, Any]:
        profile = self.get_user(user_id)
        if profile is None:
            raise KeyError(f"Unknown user '{user_id}'")
        if len(audio_samples) < 3:
            raise ValueError("At least 3 audio samples are required")

        sample_paths = self._materialize_uploads(audio_samples)
        try:
            embedding = self.get_speaker_service().enroll_speaker(user_id, sample_paths)
            self.get_speaker_service().save_embedding(
                embedding,
                str(self.settings.embeddings_dir / f"{user_id}.pkl"),
            )
            return self._compose_user_profile(user_id)
        finally:
            self._cleanup_paths(sample_paths)

    def delete_user(self, user_id: str) -> None:
        if self.get_user(user_id) is None:
            raise KeyError(f"Unknown user '{user_id}'")

        embedding_path = self.settings.embeddings_dir / f"{user_id}.pkl"
        if embedding_path.exists():
            embedding_path.unlink()
        delete_tts_preferences(user_id, Config.DB_PATH)
        delete_user_profile(user_id, Config.DB_PATH)
        delete_user_record(user_id, Config.DB_PATH)

    def process_chat_query(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        selected_user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        conversation = self._get_or_create_conversation(conversation_id)
        recognized_user, warnings = self._resolve_user_reference(
            selected_user_id=selected_user_id,
            audio_path=None,
        )
        response = self._build_query_response(
            message=message,
            conversation=conversation,
            selected_user_id=selected_user_id,
            recognized_user=recognized_user,
            warnings=warnings,
        )
        response["conversation_id"] = conversation.conversation_id
        response["recognized_user"] = recognized_user
        return response

    def process_voice_query(
        self,
        audio_bytes: bytes,
        filename: str,
        conversation_id: Optional[str] = None,
        selected_user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        conversation = self._get_or_create_conversation(conversation_id)
        temp_path = self._write_temp_file(filename, audio_bytes)
        try:
            asr_result = self.get_asr_service().transcribe(temp_path)
            transcript = asr_result["text"].strip()
            normalized_transcript = asr_result.get("normalized_text", transcript).strip()
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

            recognized_user, warnings = self._resolve_user_reference(
                selected_user_id=selected_user_id,
                audio_path=temp_path,
            )
            response = self._build_query_response(
                message=transcript,
                conversation=conversation,
                selected_user_id=selected_user_id,
                recognized_user=recognized_user,
                warnings=warnings,
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
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def create_tts_preview(
        self,
        text: str,
        user_id: Optional[str] = None,
        preferences: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        audio_url, warnings = self._synthesize_audio(
            text=text,
            user_id=user_id,
            preferences=preferences,
        )
        return {"audio_url": audio_url, "warnings": warnings}

    def resolve_audio_path(self, audio_id: str) -> Optional[Path]:
        candidate = (self.settings.generated_audio_dir / audio_id).resolve()
        try:
            candidate.relative_to(self.settings.generated_audio_dir.resolve())
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    def _build_query_response(
        self,
        message: str,
        conversation: ConversationState,
        selected_user_id: Optional[str],
        recognized_user: Optional[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        working_warnings = list(warnings)
        query_response = self._run_query_logic(message, conversation, working_warnings)

        audio_url = None
        if query_response["response_text"]:
            preference_source = (
                selected_user_id
                or (recognized_user["user_id"] if recognized_user else None)
            )
            audio_url, tts_warnings = self._synthesize_audio(
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
        intent_type = (
            "quote_lookup"
            if original_lower.startswith(("who said ", "who wrote "))
            else intent["type"]
        )

        if intent["type"] == "author_search":
            results = self.search_service.search_by_author(intent["author"], limit=intent["limit"])
            query_label = intent["author"]
        else:
            results = self.search_service.search_quotes(intent["query"], limit=max(intent["limit"], 5))
            query_label = intent["query"]

        if not results:
            response_text = f"I could not find an exact match for '{query_label}'. Please try again or rephrase."
            warnings.append("no_quote_found")
            self._record_conversation(
                conversation,
                user_message=message,
                response_text=response_text,
                results=[],
                intent_type=intent_type,
            )
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

        self._record_conversation(
            conversation,
            user_message=message,
            response_text=response_text,
            results=[dict(result) for result in results],
            intent_type=intent_type,
        )
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
    ) -> Optional[dict[str, Any]]:
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

    def _format_primary_response(
        self,
        intent_type: str,
        query_label: str,
        quote: dict[str, Any],
    ) -> str:
        quote_text = quote["quote_text"]
        author = quote["author_name"]
        source = quote["source_title"]

        if intent_type == "author_search":
            return f'Here is a quote by {author}: "{quote_text}" from {source}.'
        if intent_type == "quote_lookup":
            return f'The best matching quote is "{quote_text}" by {author} from {source}.'
        if intent_type == "follow_up_alternative":
            return f'Here is another quote: "{quote_text}" by {author} from {source}.'
        return f'Here is a quote about {query_label}: "{quote_text}" by {author} from {source}.'

    def _synthesize_audio(
        self,
        text: str,
        user_id: Optional[str] = None,
        preferences: Optional[dict[str, Any]] = None,
    ) -> tuple[Optional[str], list[str]]:
        warnings: list[str] = []
        primary_filename = f"{uuid.uuid4().hex}.wav"
        primary_path = self.settings.generated_audio_dir / primary_filename

        try:
            self.get_tts_service().synthesize_personalized(
                text=text,
                user_id=user_id,
                output_path=str(primary_path),
                preferences=preferences,
            )
            return self.audio_url_for(primary_filename), warnings
        except Exception:
            warnings.append("tts_fallback")

        fallback_filename = f"{uuid.uuid4().hex}.mp3"
        fallback_path = self.settings.generated_audio_dir / fallback_filename
        try:
            self.get_simple_tts_service().synthesize_personalized(
                text=text,
                user_id=user_id,
                output_path=str(fallback_path),
                preferences=preferences,
            )
            return self.audio_url_for(fallback_filename), warnings
        except Exception:
            warnings.append("tts_unavailable")
            return None, warnings

    def audio_url_for(self, audio_id: str) -> str:
        return f"{self.settings.api_prefix}/audio/{audio_id}"

    def _resolve_user_reference(
        self,
        selected_user_id: Optional[str],
        audio_path: Optional[str],
    ) -> tuple[Optional[dict[str, Any]], list[str]]:
        warnings: list[str] = []

        if selected_user_id:
            profile = self.get_user(selected_user_id)
            if profile is None:
                warnings.append("selected_user_not_found")
                return None, warnings
            return {
                "user_id": profile["user_id"],
                "display_name": profile["display_name"],
                "confidence": 1.0,
                "source": "selected",
            }, warnings

        if not audio_path:
            return None, warnings

        enrolled_users = self.get_speaker_service().load_all_embeddings(str(self.settings.embeddings_dir))
        if not enrolled_users:
            warnings.append("speaker_not_recognized")
            return None, warnings

        matched_user, confidence = self.get_speaker_service().identify_speaker(audio_path, enrolled_users)
        if not matched_user:
            warnings.append("speaker_not_recognized")
            return None, warnings

        profile = self.get_user(matched_user) or {
            "user_id": matched_user,
            "display_name": matched_user,
        }
        return {
            "user_id": profile["user_id"],
            "display_name": profile["display_name"],
            "confidence": confidence,
            "source": "speaker_id",
        }, warnings

    def _get_or_create_conversation(self, conversation_id: Optional[str]) -> ConversationState:
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
        conversation.history = conversation.history[-(self.settings.conversation_history_limit * 2) :]
        conversation.last_query = user_message
        conversation.last_results = results
        conversation.last_response_text = response_text
        conversation.last_intent_type = intent_type
        conversation.last_result_index = 0

    def _compose_user_profile(self, user_id: str) -> dict[str, Any]:
        profile = get_user_profile(user_id, Config.DB_PATH) or {
            "user_id": user_id,
            "display_name": user_id,
            "group_identifier": None,
        }
        preferences = get_tts_preferences(user_id, Config.DB_PATH)
        return {
            "user_id": user_id,
            "display_name": profile["display_name"],
            "group_identifier": profile.get("group_identifier"),
            "has_embedding": (self.settings.embeddings_dir / f"{user_id}.pkl").exists(),
            "preferences": preferences,
        }

    def _all_known_user_ids(self) -> list[str]:
        user_ids = {profile["user_id"] for profile in list_user_profiles(Config.DB_PATH)}
        user_ids.update(list_tts_preference_users(Config.DB_PATH))
        user_ids.update(path.stem for path in self.settings.embeddings_dir.glob("*.pkl"))
        return sorted(user_ids)

    def _slugify_user_id(self, display_name: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
        return normalized

    def _materialize_uploads(self, samples: list[tuple[str, bytes]]) -> list[str]:
        temp_paths: list[str] = []
        for filename, payload in samples:
            temp_paths.append(self._write_temp_file(filename, payload))
        return temp_paths

    def _write_temp_file(self, filename: str, payload: bytes) -> str:
        suffix = Path(filename or "sample.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(payload)
            return temp_file.name

    def _cleanup_paths(self, paths: list[str]) -> None:
        for path in paths:
            if os.path.exists(path):
                os.unlink(path)

    def _dedupe_preserve_order(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered
