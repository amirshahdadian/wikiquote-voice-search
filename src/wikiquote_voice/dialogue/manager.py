"""Dialogue manager coordinating intent parsing, search and generation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .adapters import GraphSearchAdapter, QuoteResult
from .intents import Intent, IntentParser, IntentResult
from .nlg import NLGTemplates, UserPreferences

logger = logging.getLogger(__name__)


@dataclass
class DialogueState:
    """State tracker for an interactive search session."""

    last_intent: Optional[Intent] = None
    last_topic: Optional[str] = None
    last_author: Optional[str] = None
    last_results: List[QuoteResult] = field(default_factory=list)
    current_index: int = -1
    current_quote: Optional[QuoteResult] = None
    favorites: List[QuoteResult] = field(default_factory=list)
    preferences: UserPreferences = field(default_factory=UserPreferences)

    def as_context(self) -> Dict[str, Optional[str]]:
        return {
            "last_intent": self.last_intent.value if self.last_intent else None,
            "last_topic": self.last_topic,
            "last_author": self.last_author,
        }


class DialogueManager:
    """High-level coordinator that turns user utterances into responses."""

    def __init__(
        self,
        search_adapter: Optional[GraphSearchAdapter],
        intent_parser: Optional[IntentParser] = None,
        nlg: Optional[NLGTemplates] = None,
        search_limit: int = 5,
    ) -> None:
        self.search_adapter = search_adapter
        self.intent_parser = intent_parser or IntentParser()
        self.nlg = nlg or NLGTemplates()
        self.search_limit = search_limit
        self.state = DialogueState()

    def handle_utterance(self, utterance: str) -> str:
        """Process a user utterance and produce a natural language reply."""

        intent_result = self.intent_parser.parse(utterance, self.state.as_context())
        logger.debug("Detected intent %s with slots %s", intent_result.intent, intent_result.slots)

        handler = {
            Intent.SEARCH_TOPIC: self._handle_search_topic,
            Intent.SEARCH_AUTHOR: self._handle_search_author,
            Intent.ANOTHER: self._handle_another,
            Intent.REPEAT: self._handle_repeat,
            Intent.SHORTER: self._handle_shorter,
            Intent.LONGER: self._handle_longer,
            Intent.FAVORITE: self._handle_favorite,
        }.get(intent_result.intent, self._handle_unknown)

        response = handler(intent_result)
        self.state.last_intent = intent_result.intent
        return response

    def set_user_style(self, style: str) -> None:
        """Update the preferred NLG style for future responses."""

        self.state.preferences.style = style

    def set_tts_preferences(
        self,
        *,
        voice: Optional[str] = None,
        rate_wpm: Optional[int] = None,
        pitch: Optional[int] = None,
    ) -> None:
        """Adjust speech synthesis preferences for downstream playback."""

        if voice is not None:
            self.state.preferences.voice = voice
        if rate_wpm is not None:
            self.state.preferences.rate_wpm = rate_wpm
        if pitch is not None:
            self.state.preferences.pitch = pitch

    def close(self) -> None:
        """Release any external resources held by the manager."""

        if self.search_adapter:
            self.search_adapter.close()

    # Intent handlers -----------------------------------------------------

    def _handle_search_topic(self, intent_result: IntentResult) -> str:
        topic = intent_result.slots.get("topic") or self.state.last_topic
        if not topic:
            return self.nlg.format_missing_query("topic", self.state.preferences)

        if not self.search_adapter:
            return self.nlg.format_backend_error(self.state.preferences)

        try:
            quotes = self.search_adapter.search_topic(topic, limit=self.search_limit)
        except Exception:
            logger.exception("Failed to retrieve topic quotes for '%s'", topic)
            return self.nlg.format_backend_error(self.state.preferences)

        if not quotes:
            self._reset_results()
            self.state.last_topic = topic
            return self.nlg.format_no_results("topic", topic, self.state.preferences)

        self.state.last_results = quotes
        self.state.current_index = 0
        self.state.current_quote = quotes[0]
        self.state.last_topic = topic
        self.state.last_author = quotes[0].author
        return self.nlg.format_topic_result(topic, quotes[0], self.state.preferences)

    def _handle_search_author(self, intent_result: IntentResult) -> str:
        author = intent_result.slots.get("author") or self.state.last_author
        if not author:
            return self.nlg.format_missing_query("author", self.state.preferences)

        if not self.search_adapter:
            return self.nlg.format_backend_error(self.state.preferences)

        try:
            quotes = self.search_adapter.search_author(author, limit=self.search_limit)
        except Exception:
            logger.exception("Failed to retrieve author quotes for '%s'", author)
            return self.nlg.format_backend_error(self.state.preferences)

        if not quotes:
            self._reset_results()
            self.state.last_author = author
            return self.nlg.format_no_results("author", author, self.state.preferences)

        self.state.last_results = quotes
        self.state.current_index = 0
        self.state.current_quote = quotes[0]
        self.state.last_author = author
        self.state.last_topic = None
        return self.nlg.format_author_result(author, quotes[0], self.state.preferences)

    def _handle_another(self, _: IntentResult) -> str:
        if not self.state.last_results:
            return self.nlg.format_no_active_quote(self.state.preferences)

        if self.state.current_index + 1 >= len(self.state.last_results):
            return self.nlg.format_no_more_results(self.state.preferences)

        self.state.current_index += 1
        quote = self.state.last_results[self.state.current_index]
        self.state.current_quote = quote
        return self.nlg.format_additional_quote(quote, self.state.preferences)

    def _handle_repeat(self, _: IntentResult) -> str:
        if not self.state.current_quote:
            return self.nlg.format_no_active_quote(self.state.preferences)

        return self.nlg.format_repeat(self.state.current_quote, self.state.preferences)

    def _handle_shorter(self, _: IntentResult) -> str:
        return self._handle_length_adjustment(preference="shorter")

    def _handle_longer(self, _: IntentResult) -> str:
        return self._handle_length_adjustment(preference="longer")

    def _handle_favorite(self, _: IntentResult) -> str:
        if not self.state.current_quote:
            return self.nlg.format_no_active_quote(self.state.preferences)

        quote = self.state.current_quote
        if not any(self._is_same_quote(quote, fav) for fav in self.state.favorites):
            self.state.favorites.append(quote)
        return self.nlg.format_favorite_saved(quote, self.state.preferences)

    def _handle_unknown(self, _: IntentResult) -> str:
        return self.nlg.format_unknown(self.state.preferences)

    # Helper methods ------------------------------------------------------

    def _handle_length_adjustment(self, preference: str) -> str:
        if not self.state.last_results:
            return self.nlg.format_no_active_quote(self.state.preferences)

        if preference == "shorter":
            quote = min(self.state.last_results, key=lambda q: q.length)
        else:
            quote = max(self.state.last_results, key=lambda q: q.length)

        self.state.current_quote = quote
        self.state.current_index = self.state.last_results.index(quote)
        return self.nlg.format_length_adjustment(preference, quote, self.state.preferences)

    @staticmethod
    def _is_same_quote(left: QuoteResult, right: QuoteResult) -> bool:
        return left.text == right.text and left.author == right.author

    def _reset_results(self) -> None:
        self.state.last_results.clear()
        self.state.current_index = -1
        self.state.current_quote = None
