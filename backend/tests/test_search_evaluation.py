from __future__ import annotations

import asyncio
import json
import logging
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pytest
from google import genai

from backend.app.core.logging import log_model_event
from backend.app.core.settings import Settings
from backend.app.integrations.gemini import GeminiService
from backend.app.integrations.neo4j_repository import Neo4jQuoteRepository
from backend.app.cli.ingest import stable_id
from backend.app.domain import SearchIntent
from backend.app.services.hybrid_search import HybridSearch


FIXTURE = Path(__file__).parent / "fixtures" / "search_evaluation.json"


def _load_cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _quote_id(text: str) -> str:
    normalized = " ".join(
        unicodedata.normalize("NFKC", text).casefold().split()
    )
    return stable_id(normalized)


def test_evaluation_corpus_has_fixed_reviewable_groups():
    cases = _load_cases()

    assert len(cases["intents"]) == 40
    assert len(cases["fragments"]) == 50
    assert len(cases["authors"]) == 20
    assert len(cases["topics"]) == 40
    assert {
        kind: sum(expected == kind for _, expected in cases["intents"])
        for kind in {
            "topic",
            "author",
            "quote_fragment",
            "random",
            "repeat",
            "alternative",
            "attribution",
        }
    } == {
        "topic": 10,
        "author": 10,
        "quote_fragment": 8,
        "random": 4,
        "repeat": 3,
        "alternative": 3,
        "attribution": 2,
    }


def test_model_logging_contains_metadata_only(caplog):
    with caplog.at_level(logging.INFO):
        log_model_event(
            event="query",
            model="gemini-test",
            latency_ms=12,
            intent="topic",
            input_tokens=7,
            output_tokens=2,
            fallback="none",
        )

    assert "event=query model=gemini-test intent=topic latency_ms=12" in caplog.text
    assert "input_tokens=7 output_tokens=2 fallback=none" in caplog.text


@dataclass
class EvaluationResults:
    intent_correct: int
    fragment_hits_at_5: int
    author_hits_at_5: int
    topic_hits_at_10: int


@pytest.fixture(scope="module")
def evaluation_results():
    if os.getenv("RUN_LIVE_EVALUATION") != "1":
        pytest.skip("set RUN_LIVE_EVALUATION=1 to use Gemini and Neo4j")
    settings = Settings()
    if settings.gemini_api_key is None:
        pytest.skip("GEMINI_API_KEY is required")

    cases = _load_cases()
    client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
    gemini = GeminiService(
        client,
        settings.gemini_llm_model,
        settings.gemini_embedding_model,
        settings.gemini_embedding_dimensions,
    )
    repository = Neo4jQuoteRepository(
        settings.neo4j_uri,
        settings.neo4j_username,
        settings.neo4j_password,
    )
    search = HybridSearch(repository, gemini)
    try:
        predicted = [
            asyncio.run(gemini.interpret(query, [])).kind
            for query, _ in cases["intents"]
        ]
        intent_correct = sum(
            actual == expected
            for actual, (_, expected) in zip(predicted, cases["intents"])
        )
        fragment_hits = sum(
            _quote_id(full_quote)
            in {
                hit.quote_id
                for hit in repository.lexical_search(fragment, 5)
            }
            for fragment, full_quote in cases["fragments"]
        )
        author_hits = sum(
            any(
                (hit.author_name or "").casefold() == expected.casefold()
                for hit in repository.author_search(query, 5)
            )
            for query, expected in cases["authors"]
        )
        topic_hits = sum(
            bool(
                {
                    _quote_id(quote)
                    for quote in acceptable_quotes
                }
                & {
                    hit.quote_id
                    for hit in asyncio.run(
                        search.search(
                            SearchIntent(
                                kind="topic",
                                search_text=query,
                                limit=10,
                            )
                        )
                    )
                }
            )
            for query, acceptable_quotes in cases["topics"]
        )
        return EvaluationResults(
            intent_correct,
            fragment_hits,
            author_hits,
            topic_hits,
        )
    finally:
        repository.close()
        client.close()


@pytest.mark.integration
def test_intent_accuracy(evaluation_results):
    assert evaluation_results.intent_correct / 40 >= 0.95


@pytest.mark.integration
def test_exact_fragment_recall_at_five(evaluation_results):
    assert evaluation_results.fragment_hits_at_5 / 50 >= 0.96


@pytest.mark.integration
def test_author_recall_at_five(evaluation_results):
    assert evaluation_results.author_hits_at_5 / 20 >= 0.95


@pytest.mark.integration
def test_topic_recall_at_ten(evaluation_results):
    assert evaluation_results.topic_hits_at_10 / 40 >= 0.85


@pytest.mark.integration
def test_intent_model_price_benchmark():
    if os.getenv("RUN_MODEL_BENCHMARK") != "1":
        pytest.skip("set RUN_MODEL_BENCHMARK=1 for the two-model paid benchmark")
    settings = Settings()
    if settings.gemini_api_key is None:
        pytest.skip("GEMINI_API_KEY is required")

    cases = _load_cases()["intents"]
    client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
    try:
        scores = {}
        for model in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"):
            service = GeminiService(
                client,
                model,
                settings.gemini_embedding_model,
                settings.gemini_embedding_dimensions,
            )
            scores[model] = sum(
                asyncio.run(service.interpret(query, [])).kind == expected
                for query, expected in cases
            )
        assert scores["gemini-3.5-flash-lite"] / 40 >= 0.95
        if scores["gemini-3.1-flash-lite"] / 40 >= 0.95:
            assert scores["gemini-3.1-flash-lite"] >= scores[
                "gemini-3.5-flash-lite"
            ]
    finally:
        client.close()
