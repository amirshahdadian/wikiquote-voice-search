from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

# Domain

IntentKind = Literal[
    "topic",
    "author",
    "quote_fragment",
    "random",
    "repeat",
    "alternative",
    "attribution",
]


class SearchIntent(BaseModel):
    kind: IntentKind
    search_text: str = ""
    author: str = ""
    limit: int = Field(default=5, ge=1, le=10)


class QuoteHit(BaseModel):
    quote_id: str
    quote_text: str
    author_name: str | None = None
    source_title: str | None = None
    citation: str | None = None
    page_title: str
    relevance_score: float
    search_type: str


class QueryState(TypedDict, total=False):
    intent: SearchIntent
    hits: list[QuoteHit]
    result_index: int
    response_text: str
    warnings: list[str]
    history: list[dict[str, str]]


# Api

class UserPreferences(BaseModel):
    speaking_rate: float = Field(default=1.0, ge=0.5, le=1.5)
    energy_scale: float = Field(default=1.0, ge=0.5, le=1.5)
    style: str = "neutral"


class UserProfile(BaseModel):
    user_id: str
    display_name: str
    group_identifier: str | None = None
    has_embedding: bool = False
    preferences: UserPreferences | None = None


class RecognizedUser(BaseModel):
    user_id: str
    display_name: str
    confidence: float | None = None
    source: str


class HealthResponse(BaseModel):
    search: bool
    asr: bool
    speaker_id: bool
    tts: bool
    sqlite: bool


class ChatQueryRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    selected_user_id: str | None = None


class ChatQueryResponse(BaseModel):
    conversation_id: str
    recognized_user: RecognizedUser | None = None
    intent_type: str
    response_text: str
    best_quote: QuoteHit | None = None
    related_quotes: list[QuoteHit] = Field(default_factory=list)
    audio_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class VoiceQueryResponse(ChatQueryResponse):
    transcript: str


class TTSPreviewRequest(BaseModel):
    text: str = Field(min_length=1)
    user_id: str | None = None
    preferences: UserPreferences | None = None


class TTSPreviewResponse(BaseModel):
    audio_url: str | None = None
    warnings: list[str] = Field(default_factory=list)
