"""Author endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.dependencies import get_quote_search_service
from backend.app.api.schemas import AuthorResult
from backend.app.services import QuoteSearchService

router = APIRouter(prefix="/api/authors", tags=["authors"])


@router.get("/popular", response_model=list[AuthorResult])
def get_popular_authors(
    limit: int = Query(default=20, ge=1, le=50),
    search_service: QuoteSearchService = Depends(get_quote_search_service),
) -> list[AuthorResult]:
    return [AuthorResult(**author) for author in search_service.get_popular_authors(limit=limit)]
