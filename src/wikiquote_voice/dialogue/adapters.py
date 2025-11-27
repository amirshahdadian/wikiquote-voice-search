"""Adapter that connects the dialogue manager to the Neo4j quote search service."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from ..search import QuoteSearchService

logger = logging.getLogger(__name__)


@dataclass
class QuoteResult:
    """Normalized representation of a quote returned by the graph search."""

    text: str
    author: Optional[str] = None
    source: Optional[str] = None
    relevance: Optional[float] = None

    @property
    def length(self) -> int:
        """Return the character length of the quote text for comparison."""

        return len(self.text or "")


class GraphSearchAdapter:
    """Wrapper around :class:`QuoteSearchService` with dialogue-friendly results."""

    def __init__(self, search_service: QuoteSearchService):
        self._search_service = search_service
        self._connected = False

    @classmethod
    def from_config(cls) -> "GraphSearchAdapter":
        """Instantiate an adapter using credentials from :mod:`config`."""

        from ..config import Config  # Imported lazily to avoid import cycles during testing.

        service = QuoteSearchService(
            Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD
        )
        return cls(service)

    def connect(self) -> None:
        """Ensure an active connection to the Neo4j instance."""

        if not self._connected:
            logger.debug("Connecting graph search adapter to Neo4j")
            self._search_service.connect()
            self._connected = True

    def close(self) -> None:
        """Close the Neo4j driver connection if it is active."""

        if self._connected:
            logger.debug("Closing graph search adapter connection")
            self._search_service.close()
            self._connected = False

    def search_topic(self, topic: str, limit: int = 5) -> List[QuoteResult]:
        """Return quotes that mention the requested topic."""

        self.connect()
        try:
            results = self._search_service.autocomplete(topic, limit=limit)
        except Exception:
            logger.exception("Topic search failed for '%s'", topic)
            raise
        return [self._normalize_record(record) for record in results]

    def search_author(self, author: str, limit: int = 5) -> List[QuoteResult]:
        """Return quotes attributed to the requested author."""

        self.connect()
        try:
            results = self._search_service.search_by_author(author, limit=limit)
        except Exception:
            logger.exception("Author search failed for '%s'", author)
            raise
        return [self._normalize_record(record) for record in results]

    @staticmethod
    def _normalize_record(record: dict) -> QuoteResult:
        return QuoteResult(
            text=record.get("quote_text", "").strip(),
            author=record.get("author_name"),
            source=record.get("source_title"),
            relevance=record.get("relevance_score"),
        )
