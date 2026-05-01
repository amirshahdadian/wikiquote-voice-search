"""Quote search service backed by Neo4j."""
from __future__ import annotations

from backend.app.core.settings import Settings
from backend.app.integrations.neo4j_quotes import QuoteSearchService as Neo4jQuoteSearch


class QuoteSearchService:
    """High-level quote search service used by HTTP handlers and workflows."""

    def __init__(self, app_settings: Settings):
        self._repository = Neo4jQuoteSearch(
            app_settings.neo4j_uri,
            app_settings.neo4j_username,
            app_settings.neo4j_password,
            app_settings.neo4j_database,
        )
        self._repository.connect()
        self._repository.build_semantic_index(sample_size=10000)

    @property
    def repository(self) -> Neo4jQuoteSearch:
        return self._repository

    def close(self) -> None:
        self._repository.close()

    def __getattr__(self, name: str):
        return getattr(self._repository, name)
