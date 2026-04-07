import os
import unittest

os.environ.setdefault("NEO4J_PASSWORD", "test-password")

from scripts.parse_wikitext import ExtractedQuote, MWParserQuoteExtractor


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

    def test_person_pages_like_steve_jobs_and_jfk_are_classified_correctly(self):
        steve_jobs = """
'''[[w:Steve Jobs|Steven Paul Jobs]]''' (1955–2011) was the chairman and CEO of Apple Inc.

== Quotes ==
=== 1980s ===
* Real artists ship.
** As quoted in ''West of Eden''
"""
        jfk = """
'''[[w:John F. Kennedy|John Fitzgerald Kennedy]]''' (1917–1963), often referred to as JFK, was the 35th president of the United States.

== Quotes ==
* Ask not what your country can do for you.
"""
        self.assertEqual(self.extractor._classify_page("Steve Jobs", steve_jobs).page_type, "person")
        self.assertEqual(self.extractor._classify_page("John F. Kennedy", jfk).page_type, "person")

    def test_literary_work_pages_are_not_misclassified_as_people(self):
        twelfth_night = """
{{italic title}}
'''''[[w:Twelfth Night|Twelfth Night]]''''' is a comedy by [[William Shakespeare]].

== Quotes ==
* If music be the food of love, play on.
"""
        anna_karenina = """
{{italic title}}
'''''[[w:Anna Karenina|Anna Karenina]]''''' is a novel by the Russian writer [[Leo Tolstoy]].

== Quotes ==
* Happy families are all alike; every unhappy family is unhappy in its own way.
"""
        twelfth_meta = self.extractor._classify_page("Twelfth Night", twelfth_night)
        anna_meta = self.extractor._classify_page("Anna Karenina", anna_karenina)
        self.assertEqual(twelfth_meta.page_type, "literary_work")
        self.assertEqual(twelfth_meta.default_author, "William Shakespeare")
        self.assertEqual(anna_meta.page_type, "literary_work")
        self.assertEqual(anna_meta.default_author, "Leo Tolstoy")

    def test_disambiguation_pages_are_excluded(self):
        wikitext = """
'''To Kill a Mockingbird''' can refer to either:

* [[To Kill a Mockingbird (novel)]]
* [[To Kill a Mockingbird (film)]]

{{disambig}}
"""
        metadata = self.extractor._classify_page("To Kill a Mockingbird", wikitext)
        self.assertEqual(metadata.page_type, "list_page")
        self.assertFalse(self.extractor._should_process_page("To Kill a Mockingbird", wikitext))

    def test_compilation_pages_are_excluded(self):
        proverbs = """
'''English proverbs''' is a collection of traditional sayings.

== A ==
* A stitch in time saves nine.
"""
        opening_lines = """
'''Opening lines''' collects memorable first lines from books.

* Call me Ishmael.
"""
        self.assertEqual(self.extractor._classify_page("English proverbs", proverbs).page_type, "list_page")
        self.assertEqual(self.extractor._classify_page("Opening lines", opening_lines).page_type, "list_page")
        self.assertFalse(self.extractor._should_process_page("English proverbs", proverbs))
        self.assertFalse(self.extractor._should_process_page("Opening lines", opening_lines))

    def test_season_pages_are_classified_as_tv_show(self):
        wikitext = """
'''''[[w:One Tree Hill|One Tree Hill]]''''' is a television series.

== Episode 1 ==
* Knowledge is power.
"""
        metadata = self.extractor._classify_page("One Tree Hill (Season 1)", wikitext)
        self.assertEqual(metadata.page_type, "tv_show")

    def test_tv_show_transcript_sections_are_excluded(self):
        """TV/film pages now only extract from Taglines sections.

        Full dialogue transcripts inflate the corpus by orders of magnitude;
        the best-practice approach (per the QuoteKG paper) is to skip them
        entirely and only extract curated taglines.
        """
        wikitext = """
'''''[[w:Firefly (TV series)|Firefly]]''''' (2002–2003) is a television series.

== Season One ==
=== ''Serenity'' [1.1] ===
:'''Mal''': We got some local color happening.
:'''Wash''': I am a leaf on the wind, watch how I soar.
* Shepherd Book: I am a Shepherd. Folks like a man of God.
"""
        quotes = self.extractor._extract_quotes_from_page(wikitext, "Firefly (TV series)")
        # Season sections are transcript — should be dropped entirely
        self.assertEqual(len(quotes), 0)

    def test_tv_show_taglines_are_extracted(self):
        """TV/film taglines ARE curated content and must still be extracted."""
        wikitext = """
'''''[[w:Firefly (TV series)|Firefly]]''''' (2002–2003) is a television series.

== Taglines ==
* You can't stop the signal, Mal. Everything goes somewhere.
"""
        quotes = self.extractor._extract_quotes_from_page(wikitext, "Firefly (TV series)")
        self.assertGreater(len(quotes), 0)
        self.assertEqual(quotes[0].page_type, "tv_show")

    def test_structural_author_sections_are_dropped(self):
        wikitext = """
'''''[[w:It's a Wonderful Life|It's a Wonderful Life]]''''' is a film.

== Cast ==
* Jimmy Stewart - George Bailey
* Donna Reed - Mary Hatch Bailey
"""
        quotes = self.extractor._extract_quotes_from_page(wikitext, "It's a Wonderful Life")
        finalized = [self.extractor._finalize_quote(q) for q in quotes]
        kept = [q for q in finalized if self.extractor._should_keep_finalized_quote(q)]
        self.assertEqual(kept, [])

    def test_stage_direction_only_lines_are_rejected_and_trailing_stage_directions_are_trimmed(self):
        self.assertFalse(self.extractor._is_valid_quote("[Jet brings up a wanted criminal on the monitor]"))
        self.assertEqual(
            self.extractor._strip_stage_directions("May the Force be with you. [Grogu takes one last look back]"),
            "May the Force be with you.",
        )

    def test_editorial_lines_are_rejected_as_quotes(self):
        self.assertFalse(self.extractor._is_valid_quote("From Mein Weltbild (1934), published in English as The World As I See It."))
        self.assertFalse(self.extractor._is_valid_quote("Wording in Ideas and Opinions: Everything that the human race has done and thought..."))
        self.assertFalse(self.extractor._is_valid_quote("Unsourced variants: Gravitation is not responsible for people falling in love."))
        self.assertFalse(self.extractor._is_valid_quote("German original: Dimensionslose Konstanten in den Naturgesetzen..."))
        self.assertFalse(self.extractor._is_valid_quote('"1984" redirects here. See also Nineteen Eighty-Four (film).'))
        self.assertFalse(self.extractor._is_valid_quote("Not to be confused with: Roger Bacon"))

    def test_sourced_quote_without_source_is_demoted_to_attributed(self):
        quote = self.extractor._finalize_quote(
            self.extractor._extract_quotes_from_page(
                """
'''[[w:Albert Einstein|Albert Einstein]]''' (1879–1955) was a physicist.

== Quotes ==
* Blind obedience to authority is the greatest enemy of truth.
""",
                "Albert Einstein",
            )[0]
        )
        self.assertEqual(quote.quote_type, "attributed")
        self.assertIsNone(quote.source)

    def test_duplicate_detection_uses_occurrence_key_not_quote_fingerprint(self):
        first = self.extractor._finalize_quote(
            ExtractedQuote(
                quote="Imagination is more important than knowledge.",
                author="Albert Einstein",
                source="Ideas and Opinions",
                page_title="Albert Einstein",
                page_type="person",
                source_locator="1954",
                quote_type="sourced",
            )
        )
        second = self.extractor._finalize_quote(
            ExtractedQuote(
                quote="Imagination is more important than knowledge.",
                author="Albert Einstein",
                source="The Saturday Evening Post",
                page_title="Albert Einstein",
                page_type="person",
                source_locator="1929",
                quote_type="sourced",
            )
        )
        self.assertEqual(first.quote_fingerprint, second.quote_fingerprint)
        self.assertNotEqual(first.occurrence_key, second.occurrence_key)
        self.assertFalse(self.extractor.is_duplicate(first.to_dict()))
        self.assertFalse(self.extractor.is_duplicate(second.to_dict()))

    def test_fingerprint_is_content_only_independent_of_author(self):
        """Same quote text attributed to different people should share a fingerprint."""
        first = self.extractor._finalize_quote(
            ExtractedQuote(
                quote="The only thing we have to fear is fear itself.",
                author="Franklin D. Roosevelt",
                source="Inaugural Address",
                page_title="Franklin D. Roosevelt",
                page_type="person",
                quote_type="sourced",
            )
        )
        second = self.extractor._finalize_quote(
            ExtractedQuote(
                quote="The only thing we have to fear is fear itself.",
                author="Michel de Montaigne",
                source="Essays",
                page_title="Michel de Montaigne",
                page_type="person",
                quote_type="sourced",
            )
        )
        self.assertEqual(first.quote_fingerprint, second.quote_fingerprint)

    def test_quote_fingerprint_is_punctuation_insensitive(self):
        first = self.extractor._finalize_quote(
            ExtractedQuote(
                quote="To be, or not to be: that is the question.",
                author="William Shakespeare",
                source="Hamlet",
                page_title="Hamlet",
                page_type="literary_work",
                quote_type="sourced",
            )
        )
        second = self.extractor._finalize_quote(
            ExtractedQuote(
                quote=": To be or not to be that is the question",
                author="William Shakespeare",
                source="Hamlet",
                page_title="Hamlet",
                page_type="literary_work",
                quote_type="sourced",
            )
        )
        self.assertEqual(first.quote_fingerprint, second.quote_fingerprint)


    def test_generic_dialogue_lines_are_rejected(self):
        self.assertFalse(self.extractor._is_valid_quote("What do you mean?"))
        self.assertFalse(self.extractor._is_valid_quote("What are you doing?"))
        self.assertFalse(self.extractor._is_valid_quote("I don't know."))
        # But a longer, substantive quote is kept
        self.assertTrue(self.extractor._is_valid_quote(
            "What do you mean when you say the world is ending tomorrow?"
        ))

    def test_editorial_bibliographic_notes_are_rejected(self):
        self.assertFalse(self.extractor._is_valid_quote(
            "Greek Exercises (1888); at the age of fifteen, Russell used to write down his reflections"
        ))
        self.assertFalse(self.extractor._is_valid_quote(
            "Temple Grandin, Thinking in Pictures: My Life with Autism (1995), p192"
        ))

    def test_theme_page_does_not_use_title_as_author(self):
        wikitext = """
'''Love''' is a variety of feelings, states, and attitudes.

[[Category:Themes]]

== Attributed ==
* Love is the answer.
** John Lennon
"""
        meta = self.extractor._classify_page("Love", wikitext)
        self.assertEqual(meta.page_type, "theme")
        self.assertEqual(meta.default_author, "")

    def test_person_page_source_not_equal_to_author(self):
        """On person pages, source should not duplicate the author name."""
        quote = self.extractor._finalize_quote(
            ExtractedQuote(
                quote="Only in thought is man a God.",
                author="Bertrand Russell",
                source="Bertrand Russell",
                page_title="Bertrand Russell",
                page_type="person",
                quote_type="sourced",
            )
        )
        self.assertIsNone(quote.source)
        self.assertEqual(quote.author, "Bertrand Russell")

    def test_misclassified_person_page_is_corrected(self):
        """Pages where inferred_author == page_title should be person, not literary_work."""
        wikitext = """
'''[[w:Bertrand Russell|Bertrand Russell]]''' (1872–1970) was a British philosopher.

== Quotes ==
* The whole problem with the world is that fools and fanatics are always so certain of themselves.
"""
        meta = self.extractor._classify_page("Bertrand Russell", wikitext)
        self.assertEqual(meta.page_type, "person")


if __name__ == "__main__":
    unittest.main()
