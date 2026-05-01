from __future__ import annotations

from backend.app.cli.ingest import MWParserQuoteExtractor


def test_parse_attribution_recovers_theme_page_author_and_work():
    extractor = MWParserQuoteExtractor()

    author, work, locator, year = extractor._parse_attribution(
        'Martin Luther King, Jr., "I Have a Dream," speech at the Lincoln Memorial, '
        "Washington, D.C. (August 28, 1963); reported in the Congressional Record "
        "(April 18, 1968), vol. 114, p. 9165."
    )

    assert author == "Martin Luther King, Jr."
    assert work == "I Have a Dream"
    assert year == "1963"
    assert locator is None


def test_parse_attribution_recovers_plain_author_prefixes():
    extractor = MWParserQuoteExtractor()

    author, work, locator, year = extractor._parse_attribution(
        "Franklin D. Roosevelt, inaugural address (March 4, 1933); "
        "in The Public Papers and Addresses of Franklin D. Roosevelt, 1933 (1938), p. 11."
    )

    assert author == "Franklin D. Roosevelt"
    assert work == "inaugural address"
    assert year == "1933"
    assert locator is None


def test_parse_attribution_prefers_book_title_over_chapter_title():
    extractor = MWParserQuoteExtractor()

    author, work, locator, year = extractor._parse_attribution(
        "[[Charles Dickens]], ''[[A Tale of Two Cities]]'' (1859), "
        "Book I - Recalled to Life, Chapter I - The Period."
    )

    assert author == "Charles Dickens"
    assert work == "A Tale of Two Cities"
    assert locator == "Book I - Recalled to Life, Chapter I - The Period."
    assert year == "1859"


def test_infer_author_from_intro_handles_possessive_and_descriptor_forms():
    extractor = MWParserQuoteExtractor()

    tolkien_intro = (
        "The Return of the King is the third and final volume of J. R. R. Tolkien's "
        "The Lord of the Rings, following The Fellowship of the Ring and The Two Towers."
    )
    tolkien_lead = (
        "'''''[[w:The Return of the King|The Return of the King]]''''' is the third and final "
        "volume of [[J. R. R. Tolkien]]'s ''[[The Lord of the Rings]]''"
    )
    nietzsche_intro = (
        "Human, All Too Human: A Book for Free Spirits is a book by 19th century philosopher "
        "Friedrich Nietzsche, originally published in 1878."
    )
    nietzsche_lead = (
        "'''''[[w:Human, All Too Human|Human, All Too Human: A Book for Free Spirits]]''''' "
        "is a book by 19th century philosopher [[Friedrich Nietzsche]], originally published in 1878."
    )

    assert extractor._infer_author_from_intro(tolkien_intro, tolkien_lead) == "J. R. R. Tolkien"
    assert extractor._infer_author_from_intro(nietzsche_intro, nietzsche_lead) == "Friedrich Nietzsche"


def test_person_name_detection_does_not_fail_on_luther_substring():
    extractor = MWParserQuoteExtractor()

    assert extractor._looks_like_person_name("Martin Luther King, Jr.")
    assert extractor._looks_like_person_name("Martin Luther King Jr.")
