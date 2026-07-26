"""Public quote-search service."""
from __future__ import annotations

from typing import Any

from backend.app.domain import QuoteHit, SearchIntent


class QuoteSearchService:
    def __init__(self, repository: Any, hybrid_search: Any):
        self.repository = repository
        self.hybrid_search = hybrid_search

    async def search_quotes(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        hits = await self.hybrid_search.search(
            SearchIntent(kind="topic", search_text=query, limit=limit)
        )
        return [self._serialize(hit) for hit in hits]

    def autocomplete(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return [
            self._serialize(hit)
            for hit in self.repository.autocomplete(query, limit)
        ]

    def close(self) -> None:
        self.repository.close()

    @staticmethod
    def _serialize(hit: QuoteHit) -> dict[str, Any]:
        return {
            "quote_id": hit.quote_id,
            "quote_text": hit.quote_text,
            "author_name": hit.author_name,
            "source_title": hit.work_title,
            "page_title": hit.page_title,
            "citation": hit.citation,
            "relevance_score": hit.score,
            "search_type": hit.search_type,
        }
