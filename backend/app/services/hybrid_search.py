from __future__ import annotations

import asyncio
from typing import Any

from backend.app.domain import QuoteHit, SearchIntent
from backend.app.integrations.gemini import GeminiService, GeminiUnavailable


def reciprocal_rank_fusion(
    result_sets: list[list[QuoteHit]], limit: int, k: int = 60
) -> list[QuoteHit]:
    scores: dict[str, float] = {}
    hits: dict[str, QuoteHit] = {}
    for results in result_sets:
        for rank, item in enumerate(results, start=1):
            hits.setdefault(item.quote_id, item)
            scores[item.quote_id] = scores.get(item.quote_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(
        hits.values(),
        key=lambda item: (-scores[item.quote_id], item.quote_id),
    )
    return [
        item.model_copy(
            update={"score": scores[item.quote_id], "search_type": "hybrid"}
        )
        for item in ordered[:limit]
    ]


class HybridSearch:
    def __init__(self, repository: Any, gemini: GeminiService):
        self.repository = repository
        self.gemini = gemini

    async def search(self, intent: SearchIntent) -> list[QuoteHit]:
        if intent.kind == "author":
            return await asyncio.to_thread(
                self.repository.author_search, intent.search_text, intent.limit
            )
        if intent.kind == "random":
            item = await asyncio.to_thread(self.repository.random_quote)
            return [item] if item else []

        lexical = await asyncio.to_thread(
            self.repository.lexical_search, intent.search_text, max(intent.limit, 20)
        )
        if intent.kind != "topic":
            return lexical[: intent.limit]

        try:
            vector = await self.gemini.embed_query(intent.search_text)
        except GeminiUnavailable:
            return lexical[: intent.limit]
        semantic = await asyncio.to_thread(
            self.repository.vector_search, vector, max(intent.limit, 20)
        )
        return reciprocal_rank_fusion([lexical, semantic], intent.limit)
