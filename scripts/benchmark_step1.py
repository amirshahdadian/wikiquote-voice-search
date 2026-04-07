#!/usr/bin/env python3
"""Benchmark Step 1 quote autocomplete quality against curated fragments."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wikiquote_voice.config import Config
from src.wikiquote_voice.search.service import QuoteSearchService


DEFAULT_CASES_FILE = Path("benchmarks/step1_autocomplete_cases.json")


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _matches_expected(result: Dict[str, Any], case: Dict[str, Any]) -> bool:
    author = _normalize(result.get("author_name", ""))
    source = _normalize(result.get("source_title", ""))

    expected_author_any = [_normalize(item) for item in case.get("expected_author_any", [])]
    expected_source_any = [_normalize(item) for item in case.get("expected_source_any", [])]

    author_ok = True
    source_ok = True

    if expected_author_any:
        author_ok = any(term in author for term in expected_author_any)
    if expected_source_any:
        source_ok = any(term in source for term in expected_source_any)

    return author_ok and source_ok


def load_cases(path: Path) -> List[Dict[str, Any]]:
    cases = json.loads(path.read_text())
    if not isinstance(cases, list):
        raise ValueError(f"Benchmark cases file must contain a JSON list: {path}")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Step 1 autocomplete quality")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_FILE), help="Path to benchmark cases JSON")
    parser.add_argument("--top-k", type=int, default=3, help="Evaluate whether the correct result appears within top-k")
    parser.add_argument("--query-limit", type=int, default=5, help="How many search results to request per benchmark case")
    parser.add_argument("--min-top1", type=float, default=0.85, help="Minimum acceptable top-1 accuracy")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    cases = load_cases(cases_path)

    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("src.wikiquote_voice.search.service").setLevel(logging.WARNING)
    logging.getLogger("wikiquote_voice.search.service").setLevel(logging.WARNING)

    service = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
    service.connect()

    top1_hits = 0
    topk_hits = 0
    failures: List[Dict[str, Any]] = []

    try:
        for case in cases:
            query = case["query"]
            results = service.search_quotes(query, limit=args.query_limit)
            top1_ok = bool(results) and _matches_expected(results[0], case)
            topk_ok = any(_matches_expected(result, case) for result in results[: args.top_k])

            top1_hits += int(top1_ok)
            topk_hits += int(topk_ok)

            if not top1_ok:
                failures.append(
                    {
                        "query": query,
                        "expected_author_any": case.get("expected_author_any", []),
                        "expected_source_any": case.get("expected_source_any", []),
                        "top_results": [
                            {
                                "author": result.get("author_name"),
                                "source": result.get("source_title"),
                                "search_type": result.get("search_type"),
                                "page_type": result.get("page_type"),
                                "quote_type": result.get("quote_type"),
                                "quote": result.get("quote_text", "")[:180],
                            }
                            for result in results[:3]
                        ],
                    }
                )
    finally:
        service.close()

    total = len(cases)
    top1_accuracy = top1_hits / total if total else 0.0
    topk_accuracy = topk_hits / total if total else 0.0

    print(f"Cases: {total}")
    print(f"Top-1 accuracy: {top1_hits}/{total} = {top1_accuracy:.1%}")
    print(f"Top-{args.top_k} accuracy: {topk_hits}/{total} = {topk_accuracy:.1%}")
    print()

    if failures:
        print("Top-1 failures:")
        for failure in failures:
            print(json.dumps(failure, ensure_ascii=False, indent=2))
            print()

    if top1_accuracy < args.min_top1:
        print(f"Benchmark failed: top-1 accuracy {top1_accuracy:.1%} is below threshold {args.min_top1:.1%}")
        return 1

    print("Benchmark passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
