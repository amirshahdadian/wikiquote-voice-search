import asyncio

import pytest

from backend.app.domain import QuoteHit, SearchIntent
from backend.app.integrations.gemini import GeminiUnavailable
from backend.app.services.hybrid_search import HybridSearch, reciprocal_rank_fusion


def hit(quote_id: str, search_type: str = "test") -> QuoteHit:
    return QuoteHit(
        quote_id=quote_id,
        quote_text=quote_id,
        page_title="Test",
        score=1.0,
        search_type=search_type,
    )


class FakeRepository:
    def __init__(self):
        self.calls: list[str] = []

    def lexical_search(self, text, limit):
        self.calls.append("lexical")
        return [hit("shared", "lexical"), hit("lexical", "lexical")]

    def vector_search(self, vector, limit):
        self.calls.append("vector")
        return [hit("vector", "vector"), hit("shared", "vector")]

    def author_search(self, name, limit):
        self.calls.append("author")
        return [hit("author", "author")]

    def random_quote(self):
        self.calls.append("random")
        return hit("random", "random")

    def autocomplete(self, text, limit):
        self.calls.append(text)
        return [hit("apostrophe-quote", "autocomplete")]


class FakeGemini:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    async def embed_query(self, text):
        self.calls += 1
        if self.fail:
            raise GeminiUnavailable("offline")
        return [0.0] * 768


def test_rrf_rewards_results_found_by_both_indexes():
    fused = reciprocal_rank_fusion(
        [[hit("shared"), hit("lexical")], [hit("vector"), hit("shared")]],
        limit=3,
    )

    assert fused[0].quote_id == "shared"
    assert fused[0].search_type == "hybrid"


def test_topic_search_combines_lexical_and_vector_results():
    repository = FakeRepository()
    search = HybridSearch(repository, FakeGemini())

    results = asyncio.run(
        search.search(SearchIntent(kind="topic", search_text="courage"))
    )

    assert results[0].quote_id == "shared"
    assert repository.calls == ["lexical", "vector"]


def test_plain_text_search_builds_a_topic_intent():
    repository = FakeRepository()
    search = HybridSearch(repository, FakeGemini())

    results = asyncio.run(search.search_text("courage", limit=3))

    assert results[0].quote_id == "shared"


def test_embedding_failure_returns_lexical_results():
    repository = FakeRepository()
    search = HybridSearch(repository, FakeGemini(fail=True))

    results = asyncio.run(
        search.search(SearchIntent(kind="topic", search_text="courage"))
    )

    assert results[0].search_type == "lexical"
    assert repository.calls == ["lexical"]


def test_incomplete_document_embeddings_disable_semantic_search():
    repository = FakeRepository()
    gemini = FakeGemini()
    search = HybridSearch(repository, gemini, semantic_ready=False)

    results = asyncio.run(
        search.search(SearchIntent(kind="topic", search_text="courage"))
    )

    assert results[0].search_type == "lexical"
    assert repository.calls == ["lexical"]
    assert gemini.calls == 0


def test_quote_fragment_stays_lexical_only():
    repository = FakeRepository()
    gemini = FakeGemini()
    search = HybridSearch(repository, gemini)

    asyncio.run(
        search.search(
            SearchIntent(kind="quote_fragment", search_text="grace under pressure")
        )
    )

    assert repository.calls == ["lexical"]
    assert gemini.calls == 0


def test_author_and_random_intents_use_fixed_repository_methods():
    repository = FakeRepository()
    search = HybridSearch(repository, FakeGemini())

    author = asyncio.run(
        search.search(SearchIntent(kind="author", search_text="Virginia Woolf"))
    )
    random = asyncio.run(search.search(SearchIntent(kind="random")))

    assert author[0].quote_id == "author"
    assert random[0].quote_id == "random"
    assert repository.calls == ["author", "random"]


@pytest.mark.parametrize("query", ["can't stop", "cant stop", "can’t stop"])
def test_autocomplete_accepts_apostrophe_forms(query):
    repository = FakeRepository()
    search = HybridSearch(repository, FakeGemini())

    results = search.autocomplete(query, 5)

    assert results[0].quote_id == "apostrophe-quote"
