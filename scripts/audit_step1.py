#!/usr/bin/env python3
"""Audit Step 1 extraction and graph quality."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wikiquote_voice.config import Config
from src.wikiquote_voice.search.service import QuoteSearchService
from neo4j import GraphDatabase


DEFAULT_QUERIES = [
    "ask not what your country",
    "knowledge is power",
    "to be or not",
    "happy families are all alike",
]

COMPILATION_RE = re.compile(
    r"\b(proverbs?|aphorisms?|sayings?|quotations?|quotes?\s+about|opening lines|catchphrases|taglines?)\b",
    re.IGNORECASE,
)


def audit_json(path: Path) -> None:
    if not path.exists():
        print(f"JSON file not found: {path}")
        return

    data = json.loads(path.read_text())
    page_types = Counter(row.get("page_type") for row in data)
    sourced_missing = sum(1 for row in data if row.get("quote_type") == "sourced" and not row.get("source"))
    compilation_rows = sum(
        1
        for row in data
        if COMPILATION_RE.search(row.get("page_title", "") or "")
        or COMPILATION_RE.search(row.get("author", "") or "")
        or COMPILATION_RE.search(row.get("source", "") or "")
    )

    print("JSON audit")
    print(f"  rows: {len(data)}")
    print(f"  sourced rows missing source: {sourced_missing}")
    print(f"  compilation-pattern rows: {compilation_rows}")
    print(f"  top page types: {page_types.most_common(8)}")


def audit_graph(queries: Iterable[str]) -> None:
    driver = GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD),
    )
    service = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
    service.connect()

    try:
        with driver.session() as session:
            counts = session.run(
                """
                MATCH (q:Quote)
                WITH count(q) AS quotes, count(CASE WHEN coalesce(q.is_primary, false) THEN 1 END) AS primary_quotes
                MATCH (o:QuoteOccurrence)
                RETURN quotes, primary_quotes, count(o) AS occurrences,
                       count(CASE WHEN coalesce(o.is_primary, false) THEN 1 END) AS primary_occurrences
                """
            ).single()
            suspicious = session.run(
                """
                MATCH (o:QuoteOccurrence)
                WHERE coalesce(o.is_primary, false)
                  AND (
                    toLower(coalesce(o.page_title, "")) =~ '.*\\b(proverbs?|aphorisms?|sayings?|quotations?|quotes? about|opening lines|catchphrases|taglines?)\\b.*'
                    OR toLower(coalesce(o.author_name, "")) =~ '.*\\b(proverbs?|aphorisms?|sayings?|quotations?|quotes? about|opening lines|catchphrases|taglines?)\\b.*'
                    OR toLower(coalesce(o.source_title, "")) =~ '.*\\b(proverbs?|aphorisms?|sayings?|quotations?|quotes? about|opening lines|catchphrases|taglines?)\\b.*'
                  )
                RETURN count(o) AS count
                """
            ).single()["count"]

        print("Graph audit")
        print(f"  quotes: {counts['quotes']}")
        print(f"  primary quotes: {counts['primary_quotes']}")
        print(f"  occurrences: {counts['occurrences']}")
        print(f"  primary occurrences: {counts['primary_occurrences']}")
        print(f"  suspicious primary occurrences: {suspicious}")
        print()

        print("Search spot-check")
        for query in queries:
            results = service.search_quotes(query, limit=3)
            print(f"  query: {query}")
            if not results:
                print("    no results")
                continue
            for result in results:
                print(
                    "   ",
                    {
                        "author": result.get("author_name"),
                        "source": result.get("source_title"),
                        "page_type": result.get("page_type"),
                        "quote_type": result.get("quote_type"),
                        "search_type": result.get("search_type"),
                        "quote": (result.get("quote_text") or "")[:120],
                    },
                )
    finally:
        service.close()
        driver.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Step 1 extraction and graph quality")
    parser.add_argument("--json", default="data/extracted_quotes.json", help="Path to extracted quotes JSON")
    parser.add_argument("--queries", nargs="*", default=DEFAULT_QUERIES, help="Queries to inspect in search")
    args = parser.parse_args()

    audit_json(Path(args.json))
    print()
    audit_graph(args.queries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
