from __future__ import annotations

from typing import Any
import re
import unicodedata
from collections.abc import Iterable
from neo4j import GraphDatabase
from backend.models import QuoteHit


# Neo4J Schema

SCHEMA_STATEMENTS = [
    """
    CREATE CONSTRAINT quote_id_unique IF NOT EXISTS
    FOR (q:Quote) REQUIRE q.id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT attribution_id_unique IF NOT EXISTS
    FOR (a:Attribution) REQUIRE a.id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT author_key_unique IF NOT EXISTS
    FOR (a:Author) REQUIRE a.key IS UNIQUE
    """,
    """
    CREATE FULLTEXT INDEX quote_text IF NOT EXISTS
    FOR (q:Quote) ON EACH [q.text]
    OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}
    """,
    """
    CREATE FULLTEXT INDEX author_name IF NOT EXISTS
    FOR (a:Author) ON EACH [a.name]
    """,
    """
    CREATE TEXT INDEX quote_search_text IF NOT EXISTS
    FOR (q:Quote) ON (q.search_text)
    """,
]


def ensure_schema(driver: Any) -> None:
    for statement in SCHEMA_STATEMENTS:
        driver.execute_query(statement)


# Neo4J Repository

LOAD_QUERY = """
UNWIND $rows AS row
MERGE (q:Quote {id: row.quote_id})
SET q.text = row.quote,
    q.search_text = row.search_text
MERGE (a:Attribution {id: row.attribution_id})
SET a.status = row.quote_type,
    a.status_rank = row.status_rank,
    a.citation = row.citation,
    a.work_title = row.work_title,
    a.page_title = row.page_title
MERGE (q)-[:HAS_ATTRIBUTION]->(a)
FOREACH (_ IN CASE WHEN row.author_key IS NULL THEN [] ELSE [1] END |
  MERGE (author:Author {key: row.author_key})
  SET author.name = row.author_name
  MERGE (a)-[:ATTRIBUTED_TO]->(author)
)
"""

_ATTRIBUTION_SUBQUERY = """
CALL (q) {
  MATCH (q)-[:HAS_ATTRIBUTION]->(attribution:Attribution)
  OPTIONAL MATCH (attribution)-[:ATTRIBUTED_TO]->(author:Author)
  OPTIONAL MATCH (page_author:Author {key: toLower(trim(attribution.page_title))})
  RETURN coalesce(author.name, page_author.name) AS author_name,
         coalesce(author.quote_count, page_author.quote_count, 1) AS speaker_weight,
         attribution.work_title AS work_title,
         attribution.citation AS citation,
         attribution.page_title AS page_title
  ORDER BY attribution.status_rank, attribution.page_title
  LIMIT 1
}
"""

# Lucene scores term density, so a short quotation repeating two search words
# outranks a famous one that says its subject once. Neo4j exposes no BM25
# length parameter, so the text score is weighted by how much Wikiquote holds of
# the speaker, saturating so a prolific author cannot outweigh relevance itself.
_SPEAKER_PIVOT = 100.0

_LEXICAL_QUERY = (
    """
CALL db.index.fulltext.queryNodes('quote_text', $query, {limit: $candidate_limit})
YIELD node AS q, score
"""
    + _ATTRIBUTION_SUBQUERY
    + f"""
WITH q.id AS quote_id, q.text AS quote_text, author_name, work_title,
     citation, page_title,
     score * (toFloat(speaker_weight) / ({_SPEAKER_PIVOT} + speaker_weight)) AS score
ORDER BY score DESC
WITH coalesce(author_name, quote_id) AS speaker,
     collect({{quote_id: quote_id, quote_text: quote_text, author_name: author_name,
              work_title: work_title, citation: citation, page_title: page_title,
              score: score}})[0] AS best
RETURN best.quote_id AS quote_id, best.quote_text AS quote_text,
       best.author_name AS author_name, best.work_title AS work_title,
       best.citation AS citation, best.page_title AS page_title, best.score AS score
ORDER BY score DESC
LIMIT $limit
"""
)

_BEST_CLAIM_BY_AUTHOR = """
WITH q, score, author.name AS author_name, attribution
  ORDER BY attribution.status_rank, attribution.page_title
WITH q, score, author_name, head(collect(attribution)) AS attribution
RETURN q.id AS quote_id, q.text AS quote_text, author_name,
       attribution.work_title AS work_title,
       attribution.citation AS citation,
       attribution.page_title AS page_title,
       score
"""

_AUTHOR_TOPIC_QUERY = (
    """
CALL db.index.fulltext.queryNodes('quote_text', $query, {limit: $candidate_limit})
YIELD node AS q, score
MATCH (q)-[:HAS_ATTRIBUTION]->(attribution:Attribution)-[:ATTRIBUTED_TO]->(author:Author)
WHERE toLower(author.name) CONTAINS toLower($name)
"""
    + _BEST_CLAIM_BY_AUTHOR
    + """
ORDER BY score DESC
LIMIT $limit
"""
)

_RANDOM_QUERY = """
MATCH (q:Quote)-[:HAS_ATTRIBUTION]->(attribution:Attribution)-[:ATTRIBUTED_TO]->(author:Author)
WHERE NOT q.text =~ '.*[\\p{IsHebrew}\\p{IsArabic}\\p{IsHan}\\p{IsHiragana}\\p{IsKatakana}\\p{IsCyrillic}\\p{IsGreek}\\p{IsDevanagari}].*'
WITH q, attribution, author, rand() AS random
ORDER BY random, attribution.status_rank
LIMIT 1
RETURN q.id AS quote_id, q.text AS quote_text, author.name AS author_name,
       attribution.work_title AS work_title,
       attribution.citation AS citation,
       attribution.page_title AS page_title,
       1.0 AS score
"""

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

_AUTHOR_QUERY = (
    """
CALL db.index.fulltext.queryNodes('author_name', $query, {limit: 5})
YIELD node AS author, score
MATCH (q:Quote)-[:HAS_ATTRIBUTION]->(attribution:Attribution)-[:ATTRIBUTED_TO]->(author)
"""
    + _BEST_CLAIM_BY_AUTHOR
    + """
ORDER BY score DESC, quote_text
LIMIT $limit
"""
)

STATUS_RANK = {"sourced": 0, "attributed": 1, "disputed": 2}


def _status_rank(status: str) -> int:
    """Order competing claims about the same words. Anything else sorts last."""
    return STATUS_RANK.get(status, 3)


def _author_key(value: str | None) -> str | None:
    """A readable, collapsed form of the name, unique per author."""
    return " ".join(value.split()).casefold() if value and value.strip() else None


def _search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", normalized).split())


def _lucene_query(value: str, operator: str) -> str:
    cleaned = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', " ", value)
    terms = cleaned.split()
    if not terms:
        return '""'
    return f" {operator} ".join(terms)


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
        ensure_schema(self.driver)

    def is_ready(self) -> bool:
        try:
            self.driver.verify_connectivity()
            records, _, _ = self.driver.execute_query(
                """
                SHOW INDEXES YIELD name, state
                WHERE name IN $names AND state = 'ONLINE'
                RETURN count(*) AS online
                """,
                names=["quote_text", "quote_search_text", "author_name"],
            )
            return bool(records and records[0]["online"] == 3)
        except Exception:
            return False

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
        self.driver.execute_query(LOAD_QUERY, rows=rows)

    @staticmethod
    def _prepare_row(row: dict[str, Any]) -> dict[str, Any]:
        author = (row.get("author") or "").strip() or None
        work = (row.get("work") or row.get("source") or "").strip() or None
        return {
            "quote_id": row["quote_id"],
            "attribution_id": row["attribution_id"],
            "quote": row["quote"],
            "search_text": _search_text(row["quote"]),
            "page_title": row["page_title"],
            "quote_type": row["quote_type"],
            "status_rank": _status_rank(row["quote_type"]),
            "citation": row.get("citation"),
            "author_key": _author_key(author),
            "author_name": author,
            "work_title": work,
        }

    def refresh_speaker_weights(self) -> None:
        """Count each author's quotations, which is what weights the text score."""
        self.driver.execute_query(
            """
            MATCH (a:Author)<-[:ATTRIBUTED_TO]-(:Attribution)<-[:HAS_ATTRIBUTION]-(q:Quote)
            WITH a, count(DISTINCT q) AS total
            SET a.quote_count = total
            """
        )

    def verify_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for label in ("Quote", "Attribution", "Author"):
            records, _, _ = self.driver.execute_query(
                f"MATCH (n:{label}) RETURN count(n) AS count"
            )
            counts[label] = int(records[0]["count"])
        return counts

    def lexical_search(self, text: str, limit: int) -> list[QuoteHit]:
        """Search quotation text. Terms are optional; Lucene ranks the overlap."""
        return self._query_hits(
            _LEXICAL_QUERY,
            search_type="lexical",
            query=_lucene_query(text, "OR"),
            candidate_limit=1500,
            limit=limit,
        )

    def author_topic_search(
        self, text: str, author: str, limit: int
    ) -> list[QuoteHit]:
        """Search quotation text, then keep only one author's attributions."""
        return self._query_hits(
            _AUTHOR_TOPIC_QUERY,
            search_type="author_topic",
            query=_lucene_query(text, "OR"),
            name=author.strip(),
            candidate_limit=2000,
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
        """Search by author. Every part of the name is required."""
        return self._query_hits(
            _AUTHOR_QUERY,
            search_type="author",
            query=_lucene_query(name, "AND"),
            limit=limit,
        )

    def random_quote(self) -> QuoteHit | None:
        """Pick an attributed quotation the synthesizer can actually read aloud."""
        hits = self._query_hits(_RANDOM_QUERY, search_type="random")
        return hits[0] if hits else None

    def _query_hits(
        self, cypher: str, *, search_type: str, **parameters: Any
    ) -> list[QuoteHit]:
        records, _, _ = self.driver.execute_query(cypher, parameters)
        return [
            QuoteHit(
                quote_id=record["quote_id"],
                quote_text=record["quote_text"],
                author_name=record.get("author_name"),
                source_title=record.get("work_title"),
                citation=record.get("citation"),
                page_title=record["page_title"],
                relevance_score=float(record["score"]),
                search_type=search_type,
            )
            for record in records
        ]
