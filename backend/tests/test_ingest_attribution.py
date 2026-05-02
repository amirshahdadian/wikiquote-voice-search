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


def test_parse_attribution_handles_template_style_citations():
    extractor = MWParserQuoteExtractor()

    author, work, locator, year = extractor._parse_attribution(
        "title=Why Statistics?|doi=10.1126/science.1218685|journal=Science|year=2012|"
        "author=Marie Davidian and Thomas A. Louis|url=https://science.sciencemag.org/content/336/6077/12"
    )

    assert author == "Marie Davidian and Thomas A. Louis"
    assert work == "Why Statistics?"
    assert year == "2012"
    assert locator is None


def test_parse_attribution_handles_leading_author_without_comma():
    extractor = MWParserQuoteExtractor()

    author, work, locator, year = extractor._parse_attribution(
        "Edward Teller The Legacy of Hiroshima (1962), 146."
    )

    assert author == "Edward Teller"
    assert work == "The Legacy of Hiroshima"
    assert year == "1962"
    assert locator is None


def test_parse_attribution_handles_as_cited_patterns():
    extractor = MWParserQuoteExtractor()

    author, work, locator, year = extractor._parse_attribution(
        'Jerry Mander as cited in: Peter Lunenfeld, Snap to Grid, 2001. p. 29'
    )

    assert author == "Jerry Mander"
    assert year == "2001"
    assert locator is None


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


def test_infer_author_from_intro_handles_credit_and_ascribed_forms():
    extractor = MWParserQuoteExtractor()

    gibbon_intro = (
        "The History of the Decline and Fall of the Roman Empire (Vol. 1, 1776) "
        "by Edward Gibbon."
    )
    gibbon_lead = (
        "'''The History of the Decline and Fall of the Roman Empire''' (Vol. 1, 1776) "
        "by [[Edward Gibbon]]."
    )
    plutarch_intro = (
        "Moralia is a group of manuscripts traditionally ascribed to the 1st-century "
        "scholar Plutarch of Chaeronea."
    )
    plutarch_lead = (
        "'''Moralia''' is a group of manuscripts traditionally ascribed to [[Plutarch]]."
    )

    assert extractor._infer_author_from_intro(gibbon_intro, gibbon_lead) == "Edward Gibbon"
    assert extractor._infer_author_from_intro(plutarch_intro, plutarch_lead) == "Plutarch"


def test_infer_author_from_intro_handles_plain_by_form():
    extractor = MWParserQuoteExtractor()

    intro = (
        "The History of the Decline and Fall of the Roman Empire (Vol. 1, 1776) "
        "by Edward Gibbon."
    )

    assert extractor._infer_author_from_intro(intro, intro) == "Edward Gibbon"


def test_infer_author_from_intro_does_not_promote_non_author_geography_links():
    extractor = MWParserQuoteExtractor()

    intro = (
        "Black people usually refers to people of relatively recent African descent "
        "(see African diaspora), although other usages extend the term to any of the "
        "populations characterized by having a dark skin color, a definition that also "
        "includes certain populations in Oceania and Southwest Asia."
    )
    lead = (
        "'''[[w:Black People|Black people]]''' usually refers to people of relatively recent "
        "[[Africa]]n descent (see [[w:African diaspora|African diaspora]]), although other "
        "usages extend the term to any of the populations characterized by having a dark "
        "skin color, a definition that also includes certain populations in "
        "[[w:Oceania|Oceania]] and [[w:Southeast Asia|Southwest Asia]]."
    )

    assert extractor._infer_author_from_intro(intro, lead) is None


def test_person_name_detection_does_not_fail_on_luther_substring():
    extractor = MWParserQuoteExtractor()

    assert extractor._looks_like_person_name("Martin Luther King, Jr.")
    assert extractor._looks_like_person_name("Martin Luther King Jr.")


def test_page_classification_handles_person_and_work_edges():
    extractor = MWParserQuoteExtractor()

    assert extractor._looks_like_person_page(
        "James K. Morrow (born March 17, 1947) is an American novelist and short story writer.",
        "",
    )
    assert extractor._looks_like_literary_work_page(
        "The Tragedie of Macbeth (c.1605) is a play by William Shakespeare in which a brave Scottish general named Macbeth receives a prophecy from a trio of witches.",
        "",
    )


def test_page_classification_handles_entity_and_work_page_edges():
    extractor = MWParserQuoteExtractor()

    assert extractor._looks_like_person_page(
        "Nightwish is a symphonic metal band from Kitee, Finland.",
        "",
    )
    assert extractor._looks_like_person_page(
        "Dropkick Murphys are a punk band formed in the Irish Catholic working class neighborhoods of South Boston.",
        "",
    )
    assert extractor._looks_like_person_page(
        "Publius Tacitus (c. 56-117 AD), Roman orator, lawyer, and senator.",
        "",
    )
    assert not extractor._looks_like_person_page(
        "Perception is the organization, identification, and interpretation of sensory information in order to represent and understand the presented information or environment.",
        "",
    )
    assert extractor._looks_like_literary_work_page(
        "The Tao Te Ching is a Chinese classic text traditionally credited to the 6th-century BC sage Laozi.",
        "",
    )
    assert extractor._looks_like_literary_work_page(
        "Moralia is a group of manuscripts traditionally ascribed to the 1st-century scholar Plutarch of Chaeronea.",
        "",
    )
    assert not extractor._looks_like_literary_work_page(
        "The history of logarithms is the story of a correspondence between multiplication and addition that was formalized in seventeenth century Europe.",
        "",
    )


def test_page_classification_does_not_treat_historical_events_as_people():
    extractor = MWParserQuoteExtractor()

    intro = (
        "The French Revolution was an influential period of social and political upheaval "
        "in France that lasted from 1789 until 1799, and was partially carried forward by "
        "Napoleon during the later expansion of the French Empire."
    )

    assert not extractor._looks_like_person_page(intro, "")


def test_theme_pages_keep_attribution_from_sub_bullets_for_topic_pages():
    extractor = MWParserQuoteExtractor()
    wikitext = """
'''[[w:Black People|Black people]]''' usually refers to people of relatively recent [[Africa]]n descent
(see [[w:African diaspora|African diaspora]]), although other usages extend the term to any of the
populations characterized by having a dark skin color, a definition that also includes certain
populations in [[w:Oceania|Oceania]] and [[w:Southeast Asia|Southwest Asia]].

== Quotes ==
* I have a dream: That one day, down in Alabama, with its vicious racists, with its governor having his lips dripping with the words of "interposition" and "nullification" — one day right there in Alabama little black boys and black girls will be able to join hands with little white boys and white girls as sisters and brothers.
** Martin Luther King, Jr., "I Have a Dream," speech at the Lincoln Memorial, Washington, D.C. (August 28, 1963); reported in the Congressional Record (April 18, 1968), vol. 114, p. 9165.
"""

    quotes = extractor._extract_quotes_from_page(wikitext, "Black people")
    assert len(quotes) == 1
    assert quotes[0].page_type == "theme"
    assert quotes[0].author == "Martin Luther King, Jr."
    assert quotes[0].work == "I Have a Dream"


def test_theme_pages_do_not_default_event_title_as_author():
    extractor = MWParserQuoteExtractor()
    wikitext = """
The '''[[w:French Revolution|French Revolution]]''' was an influential period of social and political upheaval in [[France]] that lasted from 1789 until 1799, and was partially carried forward by [[Napoleon]] during the later expansion of the [[w:First French Empire|French Empire]].

== A - F ==
* It was the best of times, it was the worst of times, . . . it was the spring of hope, it was the winter of despair, we had everything before us, we had nothing before us.
** [[Charles Dickens]], ''[[A Tale of Two Cities]]'' (1859), Book I - Recalled to Life, Chapter I - The Period.
"""

    quotes = extractor._extract_quotes_from_page(wikitext, "French Revolution")
    assert len(quotes) == 1
    assert quotes[0].page_type == "theme"
    assert quotes[0].author == "Charles Dickens"
    assert quotes[0].work == "A Tale of Two Cities"


def test_validation_keeps_long_canonical_quotes():
    extractor = MWParserQuoteExtractor()

    quote = (
        "This is preeminently the time to speak the truth, the whole truth, frankly and boldly. "
        "Nor need we shrink from honestly facing conditions in our country today. This great Nation "
        "will endure as it has endured, will revive and will prosper. So, first of all, let me assert "
        "my firm belief that the only thing we have to fear is fear itself — nameless, unreasoning, "
        "unjustified terror which paralyzes needed efforts to convert retreat into advance. In every "
        "dark hour of our national life a leadership of frankness and vigor has met with that "
        "understanding and support of the people themselves which is essential to victory."
    )

    assert len(quote) > 500
    assert extractor._is_valid_quote(quote)


def test_person_page_citation_commentary_does_not_override_quote_author():
    extractor = MWParserQuoteExtractor()
    wikitext = """
'''Franklin D. Roosevelt''' (1882-1945) was an American president.

== Quotes ==
* This is preeminently the time to speak the truth, the whole truth, frankly and boldly. Nor need we shrink from honestly facing conditions in our country today. This great Nation will endure as it has endured, will revive and will prosper. So, first of all, let me assert my firm belief that the only thing we have to fear is fear itself — nameless, unreasoning, unjustified terror which paralyzes needed efforts to convert retreat into advance. In every dark hour of our national life a leadership of frankness and vigor has met with that understanding and support of the people themselves which is essential to victory.
** Part of this is often misquoted as "We have nothing to fear but fear itself," most notably by [[Martin Luther King, Jr.]] in his speech.
"""

    quotes = extractor._extract_quotes_from_page(wikitext, "Franklin D. Roosevelt")
    match = next(q for q in quotes if "the only thing we have to fear is fear itself" in q.quote.lower())

    assert match.author == "Franklin D. Roosevelt"
