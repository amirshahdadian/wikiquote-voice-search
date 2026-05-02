from __future__ import annotations

from backend.app.cli.ingest import MWParserQuoteExtractor
from backend.app.integrations.neo4j_quotes import QuoteSearchService
from backend.app.search_normalization import normalize_search_text, search_text_variants


def test_normalize_search_text_removes_inline_apostrophes():
    assert normalize_search_text("That's one small step for") == "thats one small step for"
    assert normalize_search_text("Don’t stop") == "dont stop"


def test_search_text_variants_include_legacy_contraction_split():
    assert search_text_variants("thats one small step for") == [
        "thats one small step for",
        "that s one small step for",
    ]
    assert search_text_variants("that's one small step for") == [
        "thats one small step for",
        "that s one small step for",
    ]


def test_ingest_and_runtime_share_the_same_normalization():
    extractor = MWParserQuoteExtractor()
    service = QuoteSearchService("bolt://unused", "unused", "unused")

    expected = "thats one small step for"
    assert extractor._normalize_search_text("That's one small step for") == expected
    assert service._normalize_search_text("That's one small step for") == expected


def test_partial_quote_search_tries_legacy_variant_for_existing_rows():
    service = QuoteSearchService("bolt://unused", "unused", "unused")

    def fake_partial(query: str, normalized_query: str, limit: int, scope: str):
        if normalized_query == "that s one small step for":
            return [
                {
                    "quote_text": "That's one small step for [a] man, one giant leap for mankind.",
                    "author_name": "Neil Armstrong",
                    "source_title": "Moon landing",
                    "relevance_score": 1.0,
                }
            ]
        return []

    service._partial_quote_search_variant_in_scope = fake_partial  # type: ignore[method-assign]

    results = service.search_quotes("thats one small step for", limit=3)

    assert len(results) == 1
    assert results[0]["author_name"] == "Neil Armstrong"


def test_partial_quote_search_falls_back_to_full_pipeline_when_empty():
    service = QuoteSearchService("bolt://unused", "unused", "unused")

    service._partial_quote_search = lambda query, limit: []  # type: ignore[method-assign]
    service._run_search_pipeline = lambda query, limit, include_fuzzy=True: [  # type: ignore[method-assign]
        {
            "quote_text": "Your time is limited, so don't waste it living someone else's life.",
            "author_name": "Steve Jobs",
            "source_title": "Address at Stanford University (2005)",
            "relevance_score": 1.0,
        }
    ]

    results = service.search_quotes("your time is limited", limit=3)

    assert len(results) == 1
    assert results[0]["author_name"] == "Steve Jobs"


def test_search_service_allows_longer_quotes_in_results():
    assert QuoteSearchService.MAX_SEARCHABLE_QUOTE_LENGTH >= 388


def test_partial_phrase_ranking_prefers_contiguous_words_over_punctuation_breaks():
    service = QuoteSearchService("bolt://unused", "unused", "unused")

    contiguous = 'I have a dream that one day this nation will rise up.'
    interrupted = 'I have a dream: That one day, down in Alabama.'

    assert service._phrase_match_rank("i have a dream that one", contiguous) > service._phrase_match_rank(
        "i have a dream that one", interrupted
    )


def test_partial_phrase_ranking_treats_apostrophe_forms_as_contiguous():
    service = QuoteSearchService("bolt://unused", "unused", "unused")

    assert service._phrase_match_rank(
        "thats one small step for",
        "That's one small step for [a] man, one giant leap for mankind.",
    ) == 4


def test_partial_result_rerank_prefers_contiguous_phrase_even_when_longer():
    service = QuoteSearchService("bolt://unused", "unused", "unused")

    results = [
        {
            "quote_text": 'I have a dream: That one day, down in Alabama.',
            "author_name": "Martin Luther King Jr.",
            "source_title": "I Have a Dream",
            "relevance_score": 0.414,
            "quote_length": 44,
        },
        {
            "quote_text": 'I have a dream that one day this nation will rise up.',
            "author_name": "Martin Luther King Jr.",
            "source_title": "I Have a Dream",
            "relevance_score": 0.414,
            "quote_length": 53,
        },
    ]

    reranked = service._rerank_partial_quote_results("i have a dream that one", results, limit=2)

    assert reranked[0]["quote_text"] == 'I have a dream that one day this nation will rise up.'
