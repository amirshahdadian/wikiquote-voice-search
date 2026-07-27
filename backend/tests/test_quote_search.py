import asyncio

import pytest

from backend.models import QuoteHit, SearchIntent
from backend.search import QuoteSearch


def hit(quote_id: str, search_type: str = "test") -> QuoteHit:
    return QuoteHit(
        quote_id=quote_id,
        quote_text=quote_id,
        page_title="Test",
        relevance_score=1.0,
        search_type=search_type,
    )


class FakeRepository:
    def __init__(self):
        self.calls: list[str] = []
        self.parameters: dict[str, object] = {}

    def lexical_search(self, text, limit):
        self.calls.append("lexical")
        self.parameters["lexical_text"] = text
        return [hit("lexical", "lexical")]

    def author_topic_search(self, text, author, limit):
        self.calls.append("author_topic")
        self.parameters["author"] = author
        return [hit("author-topic", "author_topic")]

    def fragment_search(self, text, limit):
        self.calls.append("fragment")
        return [hit("fragment", "fragment")]

    def author_search(self, name, limit):
        self.calls.append("author")
        self.parameters["name"] = name
        return [hit("author", "author")]

    def random_quote(self):
        self.calls.append("random")
        return hit("random", "random")



def test_topic_search_uses_the_rewritten_terms_only():
    repository = FakeRepository()
    search = QuoteSearch(repository)

    results = asyncio.run(
        search.search(SearchIntent(kind="topic", search_text="mistakes learn failure"))
    )

    assert results[0].quote_id == "lexical"
    assert repository.calls == ["lexical"]
    assert repository.parameters["lexical_text"] == "mistakes learn failure"


def test_topic_search_with_a_named_person_filters_by_author():
    repository = FakeRepository()
    search = QuoteSearch(repository)

    results = asyncio.run(
        search.search(
            SearchIntent(
                kind="topic", search_text="imagination knowledge", author="Einstein"
            )
        )
    )

    assert results[0].quote_id == "author-topic"
    assert repository.calls == ["author_topic"]
    assert repository.parameters["author"] == "Einstein"


def test_an_unknown_author_keeps_the_topic_results():
    repository = FakeRepository()
    repository.author_topic_search = lambda text, author, limit: (
        repository.calls.append("author_topic") or []
    )
    search = QuoteSearch(repository)

    results = asyncio.run(
        search.search(
            SearchIntent(kind="topic", search_text="courage", author="Nobody At All")
        )
    )

    assert results[0].quote_id == "lexical"
    assert repository.calls == ["author_topic", "lexical"]


def test_plain_text_search_builds_a_topic_intent():
    search = QuoteSearch(FakeRepository())

    results = asyncio.run(search.search_text("courage", limit=3))

    assert results[0].quote_id == "lexical"


def test_quote_fragment_uses_punctuation_insensitive_fragment_search():
    repository = FakeRepository()
    search = QuoteSearch(repository)

    asyncio.run(
        search.search(
            SearchIntent(kind="quote_fragment", search_text="grace under pressure")
        )
    )

    assert repository.calls == ["fragment"]


def test_quote_fragment_falls_back_to_lexical_search():
    repository = FakeRepository()
    repository.fragment_search = lambda text, limit: (
        repository.calls.append("fragment") or []
    )
    search = QuoteSearch(repository)

    results = asyncio.run(
        search.search(
            SearchIntent(
                kind="quote_fragment",
                search_text="a long spoken quotation with one transcription difference",
            )
        )
    )

    assert results[0].quote_id == "lexical"
    assert repository.calls == ["fragment", "lexical"]


def test_author_and_random_intents_use_fixed_repository_methods():
    repository = FakeRepository()
    search = QuoteSearch(repository)

    author = asyncio.run(
        search.search(SearchIntent(kind="author", search_text="Virginia Woolf"))
    )
    random = asyncio.run(search.search(SearchIntent(kind="random")))

    assert author[0].quote_id == "author"
    assert random[0].quote_id == "random"
    assert repository.calls == ["author", "random"]


def test_author_intent_accepts_the_name_in_either_field():
    repository = FakeRepository()

    asyncio.run(
        QuoteSearch(repository).search(
            SearchIntent(kind="author", author="Virginia Woolf")
        )
    )

    assert repository.parameters["name"] == "Virginia Woolf"


@pytest.mark.parametrize("query", ["can't stop", "cant stop", "can’t stop"])
def test_autocomplete_is_the_fragment_search_and_never_calls_the_model(query):
    repository = FakeRepository()

    results = QuoteSearch(repository).autocomplete(query, 5)

    assert results[0].quote_id == "fragment"
    assert repository.calls == ["fragment"]
