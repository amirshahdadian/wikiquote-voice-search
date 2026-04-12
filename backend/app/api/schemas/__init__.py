"""Pydantic schemas for the FastAPI backend."""

from .api import (
    AuthorResult,
    ChatQueryRequest,
    ChatQueryResponse,
    HealthResponse,
    QuoteResult,
    RecognizedUser,
    TTSPreviewRequest,
    TTSPreviewResponse,
    UserPreferences,
    UserProfile,
    VoiceQueryResponse,
)

__all__ = [
    "AuthorResult",
    "ChatQueryRequest",
    "ChatQueryResponse",
    "HealthResponse",
    "QuoteResult",
    "RecognizedUser",
    "TTSPreviewRequest",
    "TTSPreviewResponse",
    "UserPreferences",
    "UserProfile",
    "VoiceQueryResponse",
]
