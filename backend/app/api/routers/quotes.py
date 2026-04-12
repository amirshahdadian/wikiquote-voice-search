"""Quote search endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.dependencies import get_quote_search_service
from backend.app.api.schemas import QuoteResult
from backend.app.services import QuoteSearchService

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("/search", response_model=list[QuoteResult])
def search_quotes(
    query: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
    search_service: QuoteSearchService = Depends(get_quote_search_service),
) -> list[QuoteResult]:
    return [QuoteResult(**quote) for quote in search_service.search_quotes(query, limit=limit)]


@router.get("/random", response_model=QuoteResult | None)
def get_random_quote(search_service: QuoteSearchService = Depends(get_quote_search_service)) -> QuoteResult | None:
    quote = search_service.get_random_quote()
    return QuoteResult(**quote) if quote else None


@router.get("/by-theme", response_model=list[QuoteResult])
def search_by_theme(
    theme: str = Query(min_length=1, description="Topic or theme (e.g. love, wisdom, courage)"),
    limit: int = Query(default=10, ge=1, le=30),
    search_service: QuoteSearchService = Depends(get_quote_search_service),
) -> list[QuoteResult]:
    return [QuoteResult(**quote) for quote in search_service.search_by_theme(theme, limit=limit)]


@router.get("/autocomplete", response_model=list[QuoteResult])
def autocomplete(
    query: str = Query(min_length=1, description="Partial quote fragment for live suggestions"),
    limit: int = Query(default=5, ge=1, le=10),
    search_service: QuoteSearchService = Depends(get_quote_search_service),
) -> list[QuoteResult]:
    return [QuoteResult(**quote) for quote in search_service.autocomplete(query, limit=limit)]


@router.get("/intelligent-search", response_model=list[QuoteResult])
def intelligent_search(
    query: str = Query(min_length=1, description="Free-form query with fuzzy matching enabled"),
    limit: int = Query(default=10, ge=1, le=30),
    search_service: QuoteSearchService = Depends(get_quote_search_service),
) -> list[QuoteResult]:
    return [QuoteResult(**quote) for quote in search_service.intelligent_search(query, limit=limit)]


@router.get("/voice-search", response_model=list[QuoteResult])
def voice_search(
    query: str = Query(min_length=1, description="Voice query text"),
    limit: int = Query(default=3, ge=1, le=10),
    search_service: QuoteSearchService = Depends(get_quote_search_service),
) -> list[QuoteResult]:
    return [QuoteResult(**quote) for quote in search_service.voice_search(query, limit=limit)]
