from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field


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
    quote_id: str
    quote_text: str
    author_name: str | None = None
    work_title: str | None = Field(default=None, serialization_alias="source_title")
    citation: str | None = None
    page_title: str
    score: float = Field(serialization_alias="relevance_score")
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
