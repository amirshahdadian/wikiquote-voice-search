"""Pydantic schemas for the FastAPI backend."""

from .api import (
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
