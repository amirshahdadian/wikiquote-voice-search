"""Dialogue management utilities for Wikiquote voice search."""

from .manager import DialogueManager, DialogueState
from .intents import Intent, IntentParser, IntentResult
from .nlg import NLGTemplates, UserPreferences
from .adapters import GraphSearchAdapter, QuoteResult

__all__ = [
    "DialogueManager",
    "DialogueState",
    "Intent",
    "IntentParser",
    "IntentResult",
    "NLGTemplates",
    "UserPreferences",
    "GraphSearchAdapter",
    "QuoteResult",
]
