from __future__ import annotations

from typing import Literal, TypedDict
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
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
    limit: int = Field(default=5, ge=1, le=10)


class QuoteHit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    quote_id: str
    quote_text: str
    author_name: str | None = None
    work_title: str | None = Field(default=None, alias="source_title")
    citation: str | None = None
    page_title: str
    score: float = Field(alias="relevance_score")
    search_type: str


class QueryState(TypedDict, total=False):
    message: str
    conversation_id: str
    intent: SearchIntent
    hits: list[QuoteHit]
    result_index: int
    response_text: str
    warnings: list[str]
    history: list[dict[str, str]]


# Api

QuoteResult = QuoteHit


class UserPreferences(BaseModel):
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


class TTSPreviewRequest(BaseModel):
    text: str = Field(min_length=1)
    user_id: Optional[str] = None
    preferences: Optional[UserPreferences] = None


class TTSPreviewResponse(BaseModel):
    audio_url: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
