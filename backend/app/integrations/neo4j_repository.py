from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from neo4j import GraphDatabase

from backend.app.domain import QuoteHit
from backend.app.integrations.neo4j_schema import ensure_schema


LOAD_QUERY = """
UNWIND $rows AS row
MERGE (q:Quote {id: row.quote_id})
SET q.text = row.quote,
    q.normalized_text = row.normalized_quote,
    q.search_text = row.search_text
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

_ATTRIBUTION_SUBQUERY = """
CALL (q) {
  MATCH (q)-[:HAS_ATTRIBUTION]->(attribution:Attribution)-[:FOUND_ON]->(page:WikiquotePage)
  OPTIONAL MATCH (attribution)-[:ATTRIBUTED_TO]->(author:Author)
  OPTIONAL MATCH (attribution)-[:FROM_WORK]->(work:Work)
  WITH attribution, page, author, work
  ORDER BY CASE attribution.status
    WHEN 'sourced' THEN 0
    WHEN 'attributed' THEN 1
    WHEN 'disputed' THEN 2
    ELSE 3
  END, page.title
  RETURN author.name AS author_name,
         work.title AS work_title,
         attribution.citation AS citation,
         page.title AS page_title
  LIMIT 1
}
"""

_LEXICAL_QUERY = (
    """
CALL db.index.fulltext.queryNodes('quote_text', $query, {limit: $candidate_limit})
YIELD node AS q, score
"""
    + _ATTRIBUTION_SUBQUERY
    + """
RETURN q.id AS quote_id, q.text AS quote_text, author_name, work_title,
       citation, page_title, score
ORDER BY score DESC
LIMIT $limit
"""
)

_VECTOR_QUERY = (
    """
MATCH (q:Quote)
  SEARCH q IN (
    VECTOR INDEX quote_embedding
    FOR $embedding
    LIMIT $candidate_limit
  ) SCORE AS score
"""
    + _ATTRIBUTION_SUBQUERY
    + """
RETURN q.id AS quote_id, q.text AS quote_text, author_name, work_title,
       citation, page_title, score
ORDER BY score DESC
LIMIT $limit
"""
)

_FRAGMENT_QUERY = (
    """
MATCH (q:Quote)
WHERE q.search_text CONTAINS $search_text
WITH q
ORDER BY size(q.search_text), q.search_text
LIMIT $limit
"""
    + _ATTRIBUTION_SUBQUERY
    + """
RETURN q.id AS quote_id, q.text AS quote_text, author_name, work_title,
       citation, page_title, 1.0 AS score
"""
)

_AUTHOR_QUERY = """
CALL db.index.fulltext.queryNodes('author_name', $query, {limit: 5})
YIELD node AS matched_author, score
MATCH (q:Quote)-[:HAS_ATTRIBUTION]->(matched_attribution:Attribution)
      -[:ATTRIBUTED_TO]->(matched_author)
WITH DISTINCT q, matched_author, score
CALL (q, matched_author) {
  MATCH (q)-[:HAS_ATTRIBUTION]->(matched_attribution:Attribution)
        -[:ATTRIBUTED_TO]->(matched_author)
  MATCH (matched_attribution)-[:FOUND_ON]->(matched_page:WikiquotePage)
  OPTIONAL MATCH (matched_attribution)-[:FROM_WORK]->(matched_work:Work)
  WITH matched_author, matched_attribution, matched_page, matched_work
  ORDER BY CASE matched_attribution.status
    WHEN 'sourced' THEN 0
    WHEN 'attributed' THEN 1
    WHEN 'disputed' THEN 2
    ELSE 3
  END, matched_page.title
  RETURN matched_author.name AS author_name,
         matched_work.title AS work_title,
         matched_attribution.citation AS citation,
         matched_page.title AS page_title
  LIMIT 1
}
RETURN q.id AS quote_id, q.text AS quote_text, author_name, work_title,
       citation, page_title, score
ORDER BY score DESC, quote_text
LIMIT $limit
"""

def _entity_key(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    normalized = " ".join(value.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", normalized).split())


def _lucene_query(value: str) -> str:
    cleaned = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', " ", value)
    terms = cleaned.split()
    if not terms:
        return '""'
    return " AND ".join(terms)


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

    def is_ready(self) -> bool:
        try:
            self.driver.verify_connectivity()
            with self.driver.session() as session:
                record = session.run(
                    """
                    SHOW INDEXES YIELD name, state
                    WHERE name IN $names AND state = 'ONLINE'
                    RETURN count(*) AS online
                    """,
                    names=[
                        "quote_text",
                        "quote_search_text",
                        "author_name",
                        "quote_embedding",
                    ],
                ).single()
            return bool(record and record["online"] == 4)
        except Exception:
            return False

    def embeddings_ready(self, model: str, dimensions: int) -> bool:
        with self.driver.session() as session:
            record = session.run(
                """
                MATCH (q:Quote)
                RETURN count(q) > 0
                   AND count(
                     CASE
                       WHEN q.embedding IS NOT NULL
                        AND q.embedding_model = $model
                        AND q.embedding_dimensions = $dimensions
                       THEN 1
                     END
                   ) = count(q) AS ready
                """,
                model=model,
                dimensions=dimensions,
            ).single()
        return bool(record and record["ready"])

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
            "search_text": _search_text(row["quote"]),
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

    def verify_counts(self, model: str, dimensions: int) -> dict[str, int]:
        labels = (
            "Quote",
            "Attribution",
            "Author",
            "Work",
            "WikiquotePage",
        )
        counts: dict[str, int] = {}
        with self.driver.session() as session:
            for label in labels:
                record = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS count"
                ).single()
                counts[label] = int(record["count"])
            record = session.run(
                """
                MATCH (q:Quote)
                WHERE q.embedding IS NULL
                   OR q.embedding_model IS NULL
                   OR q.embedding_model <> $model
                   OR q.embedding_dimensions <> $dimensions
                RETURN count(q) AS count
                """,
                model=model,
                dimensions=dimensions,
            ).single()
            counts["quotes_without_current_embedding"] = int(record["count"])
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

    def lexical_search(self, text: str, limit: int) -> list[QuoteHit]:
        return self._query_hits(
            _LEXICAL_QUERY,
            search_type="lexical",
            query=_lucene_query(text),
            candidate_limit=max(limit, 50),
            limit=limit,
        )

    def vector_search(self, vector: list[float], limit: int) -> list[QuoteHit]:
        return self._query_hits(
            _VECTOR_QUERY,
            search_type="vector",
            embedding=vector,
            candidate_limit=max(limit, 50),
            limit=limit,
        )

    def fragment_search(self, text: str, limit: int) -> list[QuoteHit]:
        return self._query_hits(
            _FRAGMENT_QUERY,
            search_type="fragment",
            search_text=_search_text(text),
            limit=limit,
        )

    def author_search(self, name: str, limit: int) -> list[QuoteHit]:
        return self._query_hits(
            _AUTHOR_QUERY,
            search_type="author",
            query=_lucene_query(name),
            limit=limit,
        )

    def autocomplete(self, text: str, limit: int) -> list[QuoteHit]:
        return self._query_hits(
            _FRAGMENT_QUERY,
            search_type="autocomplete",
            search_text=_search_text(text),
            limit=limit,
        )

    def random_quote(self) -> QuoteHit | None:
        query = (
            "MATCH (q:Quote) WITH q, rand() AS random ORDER BY random LIMIT 1\n"
            + _ATTRIBUTION_SUBQUERY
            + """
RETURN q.id AS quote_id, q.text AS quote_text, author_name, work_title,
       citation, page_title, 1.0 AS score
"""
        )
        hits = self._query_hits(query, search_type="random")
        return hits[0] if hits else None

    def _query_hits(
        self, cypher: str, *, search_type: str, **parameters: Any
    ) -> list[QuoteHit]:
        with self.driver.session() as session:
            records = session.run(cypher, parameters)
            return [
                QuoteHit(
                    quote_id=record["quote_id"],
                    quote_text=record["quote_text"],
                    author_name=record.get("author_name"),
                    work_title=record.get("work_title"),
                    citation=record.get("citation"),
                    page_title=record["page_title"],
                    score=float(record["score"]),
                    search_type=search_type,
                )
                for record in records
            ]
