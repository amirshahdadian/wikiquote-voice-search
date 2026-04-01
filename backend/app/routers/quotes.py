"""Quote search endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_backend_state
from ..schemas import QuoteResult
from ..state import BackendState

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("/search", response_model=list[QuoteResult])
def search_quotes(
    query: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
    state: BackendState = Depends(get_backend_state),
) -> list[QuoteResult]:
    return [QuoteResult(**quote) for quote in state.search_service.search_quotes(query, limit=limit)]


@router.get("/random", response_model=QuoteResult | None)
def get_random_quote(state: BackendState = Depends(get_backend_state)) -> QuoteResult | None:
    quote = state.search_service.get_random_quote()
    return QuoteResult(**quote) if quote else None
