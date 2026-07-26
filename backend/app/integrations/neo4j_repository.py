from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from neo4j import GraphDatabase

from backend.app.integrations.neo4j_schema import ensure_schema


LOAD_QUERY = """
UNWIND $rows AS row
MERGE (q:Quote {id: row.quote_id})
SET q.text = row.quote,
    q.normalized_text = row.normalized_quote
MERGE (a:Attribution {id: row.attribution_id})
SET a.status = row.quote_type,
    a.citation = row.citation,
    a.locator = row.source_locator,
    a.year = row.year,
    a.section = row.context
MERGE (p:WikiquotePage {id: row.page_id})
SET p.title = row.page_title,
    p.revision_id = row.revision_id,
    p.page_type = row.page_type
MERGE (q)-[:HAS_ATTRIBUTION]->(a)
MERGE (a)-[:FOUND_ON]->(p)
FOREACH (_ IN CASE WHEN row.author_key IS NULL THEN [] ELSE [1] END |
  MERGE (author:Author {key: row.author_key})
  SET author.name = row.author_name
  MERGE (a)-[:ATTRIBUTED_TO]->(author)
)
FOREACH (_ IN CASE WHEN row.work_key IS NULL THEN [] ELSE [1] END |
  MERGE (work:Work {key: row.work_key})
  SET work.title = row.work_title
  MERGE (a)-[:FROM_WORK]->(work)
)
"""


def _entity_key(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    normalized = " ".join(value.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class Neo4jQuoteRepository:
    def __init__(
        self,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        *,
        driver: Any | None = None,
    ):
        if driver is None and not all((uri, username, password)):
            raise ValueError("Neo4j connection settings or a driver are required")
        self.driver = driver or GraphDatabase.driver(
            uri, auth=(username, password)
        )

    def close(self) -> None:
        self.driver.close()

    def ensure_schema(self) -> None:
        with self.driver.session() as session:
            ensure_schema(session)

    def load(self, rows: Iterable[dict[str, Any]], batch_size: int = 1000) -> None:
        batch: list[dict[str, Any]] = []
        for row in rows:
            batch.append(self._prepare_row(row))
            if len(batch) == batch_size:
                self._write_batch(batch)
                batch = []
        if batch:
            self._write_batch(batch)

    def _write_batch(self, rows: list[dict[str, Any]]) -> None:
        with self.driver.session() as session:
            session.run(LOAD_QUERY, rows=rows)

    @staticmethod
    def _prepare_row(row: dict[str, Any]) -> dict[str, Any]:
        required = (
            "quote_id",
            "attribution_id",
            "quote",
            "normalized_quote",
            "page_id",
            "revision_id",
            "page_title",
            "page_type",
            "quote_type",
        )
        missing = [field for field in required if row.get(field) is None]
        if missing:
            raise ValueError(f"Quote row is missing required fields: {', '.join(missing)}")
        author = (row.get("author") or "").strip() or None
        work = (row.get("work") or row.get("source") or "").strip() or None
        return {
            "quote_id": row["quote_id"],
            "attribution_id": row["attribution_id"],
            "quote": row["quote"],
            "normalized_quote": row["normalized_quote"],
            "page_id": str(row["page_id"]),
            "revision_id": str(row["revision_id"]),
            "page_title": row["page_title"],
            "page_type": row["page_type"],
            "quote_type": row["quote_type"],
            "citation": row.get("citation"),
            "source_locator": row.get("source_locator"),
            "year": row.get("year"),
            "context": row.get("context"),
            "author_key": _entity_key(author),
            "author_name": author,
            "work_key": _entity_key(work),
            "work_title": work,
        }

    def has_legacy_schema(self) -> bool:
        with self.driver.session() as session:
            record = session.run(
                "MATCH (n) WHERE n:QuoteOccurrence OR n:Source "
                "RETURN count(n) > 0 AS legacy"
            ).single()
        return bool(record and record["legacy"])

    def verify_counts(self) -> dict[str, int]:
        labels = ("Quote", "Attribution", "Author", "Work", "WikiquotePage")
        counts: dict[str, int] = {}
        with self.driver.session() as session:
            for label in labels:
                record = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS count"
                ).single()
                counts[label] = int(record["count"])
        return counts

    def pending_embedding_rows(
        self, model: str, dimensions: int, limit: int
    ) -> list[dict[str, str]]:
        query = """
        MATCH (q:Quote)
        WHERE q.embedding IS NULL
           OR q.embedding_model IS NULL
           OR q.embedding_model <> $model
           OR q.embedding_dimensions <> $dimensions
        RETURN q.id AS quote_id, q.text AS quote_text
        ORDER BY q.id
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(
                query, model=model, dimensions=dimensions, limit=limit
            )
            return [dict(record) for record in result]

    def save_embeddings(
        self,
        records: list[dict[str, Any]],
        *,
        model: str,
        dimensions: int,
    ) -> None:
        for record in records:
            if len(record["embedding"]) != dimensions:
                raise ValueError(
                    f'Embedding for {record["quote_id"]} has the wrong dimensions'
                )
        query = """
        UNWIND $rows AS row
        MATCH (q:Quote {id: row.quote_id})
        SET q.embedding = row.embedding,
            q.embedding_model = $model,
            q.embedding_dimensions = $dimensions
        """
        with self.driver.session() as session:
            session.run(
                query,
                rows=records,
                model=model,
                dimensions=dimensions,
            )
