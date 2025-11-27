"""Natural language generation templates for the conversational agent."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .adapters import QuoteResult


@dataclass
class UserPreferences:
    """Simple user profile used to tailor responses."""

    style: str = "neutral"
    voice: str = "Alex"
    rate_wpm: int = 200
    pitch: int = 0


class NLGTemplates:
    """Collection of response templates keyed by dialogue intent."""

    STYLE_OPENERS = {
        "neutral": "Here you go.",
        "friendly": "You got it.",
        "formal": "Certainly.",
        "enthusiastic": "Great choice!",
        "concise": "",
    }

    STYLE_ERROR_OPENERS = {
        "neutral": "Sorry.",
        "friendly": "Oops!",
        "formal": "My apologies.",
        "enthusiastic": "Uh-oh!",
        "concise": "",
    }

    def format_topic_result(
        self, topic: str, quote: QuoteResult, preferences: UserPreferences
    ) -> str:
        opener = self._with_style(
            preferences.style, f"Here's a quote about {topic}.", positive=True
        )
        return self._combine(opener, self._quote_sentence(quote))

    def format_author_result(
        self, author: str, quote: QuoteResult, preferences: UserPreferences
    ) -> str:
        opener = self._with_style(
            preferences.style, f"Here's a quote by {author}.", positive=True
        )
        return self._combine(opener, self._quote_sentence(quote))

    def format_additional_quote(
        self, quote: QuoteResult, preferences: UserPreferences
    ) -> str:
        opener = self._with_style(preferences.style, "Here's another one.", positive=True)
        return self._combine(opener, self._quote_sentence(quote))

    def format_repeat(self, quote: QuoteResult, preferences: UserPreferences) -> str:
        opener = self._with_style(preferences.style, "Here it is again.", positive=True)
        return self._combine(opener, self._quote_sentence(quote))

    def format_length_adjustment(
        self, preference: str, quote: QuoteResult, preferences: UserPreferences
    ) -> str:
        if preference == "shorter":
            lead = "This one's shorter."
        else:
            lead = "Here's a longer one."
        opener = self._with_style(preferences.style, lead, positive=True)
        return self._combine(opener, self._quote_sentence(quote))

    def format_favorite_saved(
        self, quote: QuoteResult, preferences: UserPreferences
    ) -> str:
        opener = self._with_style(
            preferences.style, "Saved that quote for you.", positive=True
        )
        return self._combine(opener, self._quote_sentence(quote))

    def format_no_results(
        self, kind: str, value: str, preferences: UserPreferences
    ) -> str:
        descriptor = "that topic" if kind == "topic" else "that author"
        message = f"I couldn't find quotes for {descriptor}."
        if value:
            message = f"I couldn't find quotes for {value}."
        follow_up = "Try another topic or author."
        opener = self._with_style(preferences.style, message, positive=False)
        return self._combine(opener, follow_up)

    def format_missing_query(
        self, kind: str, preferences: UserPreferences
    ) -> str:
        if kind == "topic":
            base = "Tell me what topic you want."
        else:
            base = "Tell me which author you're after."
        return self._with_style(preferences.style, base, positive=False)

    def format_no_active_quote(self, preferences: UserPreferences) -> str:
        base = "I don't have a quote to share yet."
        follow_up = "Ask for a topic or author first."
        opener = self._with_style(preferences.style, base, positive=False)
        return self._combine(opener, follow_up)

    def format_no_more_results(self, preferences: UserPreferences) -> str:
        base = "That's all I have for now."
        follow_up = "Try a fresh search."
        opener = self._with_style(preferences.style, base, positive=False)
        return self._combine(opener, follow_up)

    def format_backend_error(self, preferences: UserPreferences) -> str:
        base = "I couldn't reach the quote database."
        follow_up = "Please try again soon."
        opener = self._with_style(preferences.style, base, positive=False)
        return self._combine(opener, follow_up)

    def format_unknown(self, preferences: UserPreferences) -> str:
        base = "I'm not sure what you need."
        follow_up = "Ask for quotes by topic or author."
        opener = self._with_style(preferences.style, base, positive=False)
        return self._combine(opener, follow_up)

    @classmethod
    def _quote_sentence(cls, quote: QuoteResult) -> str:
        parts: List[str] = [f"\"{quote.text}\""]
        if quote.author:
            parts.append(f"— {quote.author}")
        if quote.source:
            parts.append(f"({quote.source})")
        return " ".join(parts)

    def _with_style(self, style: str, message: str, positive: bool) -> str:
        mapping = self.STYLE_OPENERS if positive else self.STYLE_ERROR_OPENERS
        opener = mapping.get(style, mapping["neutral"])
        if opener:
            return f"{opener} {message}".strip()
        return message

    @staticmethod
    def _combine(*sentences: Optional[str]) -> str:
        return " ".join(sentence for sentence in sentences if sentence)
