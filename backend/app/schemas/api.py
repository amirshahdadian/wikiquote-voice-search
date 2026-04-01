"""API schemas for the FastAPI backend."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class QuoteResult(BaseModel):
    quote_text: str
    author_name: str
    source_title: str
    relevance_score: Optional[float] = None
    search_type: Optional[str] = None
    match_position: Optional[str] = None


class UserPreferences(BaseModel):
    pitch_scale: float = Field(default=1.0, ge=0.5, le=2.0)
    speaking_rate: float = Field(default=1.0, ge=0.5, le=1.5)
    energy_scale: float = Field(default=1.0, ge=0.5, le=1.5)
    style: str = "neutral"


class UserProfile(BaseModel):
    user_id: str
    display_name: str
    group_identifier: Optional[str] = None
    has_embedding: bool = False
    preferences: Optional[UserPreferences] = None


class RecognizedUser(BaseModel):
    user_id: str
    display_name: str
    confidence: Optional[float] = None
    source: str


class HealthResponse(BaseModel):
    search: bool
    asr: bool
    speaker_id: bool
    tts: bool
    sqlite: bool


class ChatQueryRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: Optional[str] = None
    selected_user_id: Optional[str] = None


class ChatQueryResponse(BaseModel):
    conversation_id: str
    recognized_user: Optional[RecognizedUser] = None
    intent_type: str
    response_text: str
    best_quote: Optional[QuoteResult] = None
    related_quotes: list[QuoteResult] = Field(default_factory=list)
    audio_url: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class VoiceQueryResponse(ChatQueryResponse):
    transcript: str
    normalized_transcript: str


class TTSPreviewRequest(BaseModel):
    text: str = Field(min_length=1)
    user_id: Optional[str] = None
    preferences: Optional[UserPreferences] = None


class TTSPreviewResponse(BaseModel):
    audio_url: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
