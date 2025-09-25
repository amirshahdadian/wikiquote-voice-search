"""Rule-based intent parser for the Wikiquote dialogue agent."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class Intent(str, Enum):
    """Enumeration of supported user intents."""

    SEARCH_TOPIC = "search_topic"
    SEARCH_AUTHOR = "search_author"
    ANOTHER = "another"
    REPEAT = "repeat"
    SHORTER = "shorter"
    LONGER = "longer"
    FAVORITE = "favorite"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Container describing the detected intent and any extracted slots."""

    intent: Intent
    slots: Dict[str, str]
    confidence: float = 1.0


class IntentParser:
    """Simple rule-based intent parser for conversational quote search."""

    _AUTHOR_PATTERNS = (
        re.compile(r"\bquotes?\s+(?:by|from)\s+(?P<author>[A-Za-z0-9 .,'\"-]+)", re.IGNORECASE),
        re.compile(r"\bfrom\s+(?P<author>[A-Za-z0-9 .,'\"-]+)\b", re.IGNORECASE),
        re.compile(r"\bby\s+(?P<author>[A-Za-z0-9 .,'\"-]+)\b", re.IGNORECASE),
        re.compile(r"\bwho\s+said\s+(?P<author>[A-Za-z0-9 .,'\"-]+)", re.IGNORECASE),
    )

    _TOPIC_PATTERNS = (
        re.compile(r"\bquotes?\s+(?:about|on|regarding|for)\s+(?P<topic>[A-Za-z0-9 .,'\"-]+)", re.IGNORECASE),
        re.compile(r"\bquote\s+about\s+(?P<topic>[A-Za-z0-9 .,'\"-]+)", re.IGNORECASE),
    )

    _CONTROL_KEYWORDS = {
        Intent.ANOTHER: ("another", "something else", "more quotes", "next one"),
        Intent.REPEAT: ("repeat", "again", "one more time", "say that again"),
        Intent.SHORTER: ("shorter", "too long", "make it brief", "smaller"),
        Intent.LONGER: ("longer", "more detail", "give me more", "full version"),
        Intent.FAVORITE: ("favorite", "save this", "bookmark", "remember that"),
    }

    _FILLER_WORDS = {
        "quote",
        "quotes",
        "show",
        "give",
        "find",
        "me",
        "some",
        "any",
        "a",
        "an",
        "the",
        "please",
    }

    def parse(self, utterance: Optional[str], context: Optional[Dict[str, str]] = None) -> IntentResult:
        """Parse a user utterance and detect the corresponding intent."""

        if not utterance:
            return IntentResult(Intent.UNKNOWN, {}, confidence=0.0)

        text = utterance.strip()
        if not text:
            return IntentResult(Intent.UNKNOWN, {}, confidence=0.0)

        normalized = re.sub(r"\s+", " ", text.lower())

        # Detect conversational control intents first.
        for intent, keywords in self._CONTROL_KEYWORDS.items():
            for keyword in keywords:
                if keyword in normalized:
                    return IntentResult(intent, {}, confidence=0.95)

        # Detect author searches.
        for pattern in self._AUTHOR_PATTERNS:
            match = pattern.search(text)
            if match:
                author = self._clean_slot(match.group("author"))
                if author:
                    return IntentResult(Intent.SEARCH_AUTHOR, {"author": author}, confidence=0.9)

        # Detect topic searches.
        for pattern in self._TOPIC_PATTERNS:
            match = pattern.search(text)
            if match:
                topic = self._clean_slot(match.group("topic"))
                if topic:
                    return IntentResult(Intent.SEARCH_TOPIC, {"topic": topic}, confidence=0.9)

        generic_match = re.search(r"quotes?\s+(?P<topic>.+)", text, re.IGNORECASE)
        if generic_match:
            topic = self._clean_slot(generic_match.group("topic"))
            topic = self._strip_leading_keywords(topic)
            if topic:
                return IntentResult(Intent.SEARCH_TOPIC, {"topic": topic}, confidence=0.6)

        # Fallback: if the utterance mentions "quote" anywhere, treat remaining words as topic.
        if "quote" in normalized:
            topic = self._extract_topic_from_keywords(text)
            if topic:
                return IntentResult(Intent.SEARCH_TOPIC, {"topic": topic}, confidence=0.5)

        return IntentResult(Intent.UNKNOWN, {}, confidence=0.2)

    def _extract_topic_from_keywords(self, text: str) -> Optional[str]:
        tokens = [token for token in re.split(r"\s+", text) if token]
        filtered = [
            token for token in tokens if token.lower() not in self._FILLER_WORDS
        ]
        topic = " ".join(filtered)
        topic = self._strip_leading_keywords(topic)
        return self._clean_slot(topic)

    @staticmethod
    def _strip_leading_keywords(value: str) -> str:
        return re.sub(r"^(about|on|regarding|for)\s+", "", value, flags=re.IGNORECASE)

    @staticmethod
    def _clean_slot(value: Optional[str]) -> str:
        if not value:
            return ""
        cleaned = value.strip(" \t\n\r'\"?.!:")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

