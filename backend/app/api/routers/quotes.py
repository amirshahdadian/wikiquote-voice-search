"""Quote search endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.dependencies import get_quote_search_service
from backend.app.api.schemas import QuoteResult
from backend.app.services import QuoteSearchService

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("/search", response_model=list[QuoteResult])
async def search_quotes(
    query: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
    search_service: QuoteSearchService = Depends(get_quote_search_service),
) -> list[QuoteResult]:
    quotes = await search_service.search_quotes(query, limit=limit)
    return [QuoteResult(**quote) for quote in quotes]


@router.get("/random", response_model=QuoteResult | None)
def get_random_quote(search_service: QuoteSearchService = Depends(get_quote_search_service)) -> QuoteResult | None:
    quote = search_service.get_random_quote()
    return QuoteResult(**quote) if quote else None


@router.get("/autocomplete", response_model=list[QuoteResult])
def autocomplete(
    query: str = Query(min_length=1, description="Partial quote fragment for live suggestions"),
    limit: int = Query(default=5, ge=1, le=10),
    search_service: QuoteSearchService = Depends(get_quote_search_service),
) -> list[QuoteResult]:
    return [QuoteResult(**quote) for quote in search_service.autocomplete(query, limit=limit)]
