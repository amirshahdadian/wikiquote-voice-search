import os
import unittest

os.environ.setdefault("NEO4J_PASSWORD", "test-password")

from scripts.parse_wikitext import MWParserQuoteExtractor


class ParseWikitextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = MWParserQuoteExtractor()

    def test_calendar_pages_are_excluded(self):
        metadata = self.extractor._classify_page("March 4", "selected by Kalki")
        self.assertEqual(metadata.page_type, "calendar_day")
        self.assertFalse(self.extractor._should_process_page("March 4", "selected by Kalki"))

    def test_qotd_boilerplate_is_not_a_quote(self):
        self.assertFalse(self.extractor._is_valid_quote("selected by Kalki"))
        self.assertFalse(self.extractor._is_valid_quote("Full text online"))

    def test_dialogue_prefix_is_split_into_speaker_and_quote(self):
        speaker, quote = self.extractor._split_speaker_prefix("Romeo: But, soft! what light through yonder window breaks?")
        self.assertEqual(speaker, "Romeo")
        self.assertEqual(quote, "But, soft! what light through yonder window breaks?")

    def test_editorial_prefix_is_not_treated_as_speaker(self):
        speaker, quote = self.extractor._split_speaker_prefix(
            "Wording in Ideas and Opinions: Everything that the human race has done and thought..."
        )
        self.assertIsNone(speaker)
        self.assertEqual(
            quote,
            "Wording in Ideas and Opinions: Everything that the human race has done and thought...",
        )

    def test_person_page_section_header_becomes_source_not_author(self):
        wikitext = """
'''[[w:Albert Einstein|Albert Einstein]]''' (1879–1955) was a physicist.

== Quotes ==
=== ''Ideas and Opinions'' ===
* Imagination is more important than knowledge.
** Source: ''Ideas and Opinions'' (1954)
"""
        quotes = self.extractor._extract_quotes_from_page(wikitext, "Albert Einstein")
        self.assertEqual(len(quotes), 1)
        quote = quotes[0]
        self.assertEqual(quote.author, "Albert Einstein")
        self.assertEqual(quote.source, "Ideas and Opinions")
        self.assertEqual(quote.work, "Ideas and Opinions")

    def test_person_page_decade_header_stays_locator_not_source(self):
        wikitext = """
'''[[w:Albert Einstein|Albert Einstein]]''' (1879–1955) was a physicist.

== Quotes ==
=== 1900s ===
* Blind obedience to authority is the greatest enemy of truth.
"""
        quotes = self.extractor._extract_quotes_from_page(wikitext, "Albert Einstein")
        self.assertEqual(len(quotes), 1)
        quote = self.extractor._finalize_quote(quotes[0])
        self.assertIsNone(quote.source)
        self.assertIsNone(quote.work)
        self.assertEqual(quote.source_locator, "1900s")

    def test_tv_show_dialogue_uses_character_as_author(self):
        wikitext = """
'''''[[w:Firefly (TV series)|Firefly]]''''' (2002–2003) is a television series.

== Season One ==
=== ''Serenity'' [1.1] ===
:'''Mal''': We got some local color happening.
"""
        quotes = self.extractor._extract_quotes_from_page(wikitext, "Firefly (TV series)")
        self.assertEqual(len(quotes), 1)
        quote = quotes[0]
        self.assertEqual(quote.page_type, "tv_show")
        self.assertEqual(quote.author, "Mal")
        self.assertEqual(quote.source, "Firefly (TV series)")

    def test_editorial_lines_are_rejected_as_quotes(self):
        self.assertFalse(self.extractor._is_valid_quote("From Mein Weltbild (1934), published in English as The World As I See It."))
        self.assertFalse(self.extractor._is_valid_quote("Wording in Ideas and Opinions: Everything that the human race has done and thought..."))
        self.assertFalse(self.extractor._is_valid_quote("Unsourced variants: Gravitation is not responsible for people falling in love."))
        self.assertFalse(self.extractor._is_valid_quote("German original: Dimensionslose Konstanten in den Naturgesetzen..."))


if __name__ == "__main__":
    unittest.main()
