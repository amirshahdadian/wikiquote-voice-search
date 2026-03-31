import unittest

from src.wikiquote_voice.search.service import QuoteSearchService


class SearchHeuristicsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QuoteSearchService("bolt://unused", "neo4j", "password")

    def test_partial_quote_detection_for_quote_fragment(self):
        self.assertTrue(self.service._looks_like_partial_quote("to be or not"))

    def test_partial_quote_detection_for_topic_query(self):
        self.assertFalse(
            self.service._looks_like_partial_quote("quotes about courage and fear")
        )

    def test_partial_quote_detection_for_author_query(self):
        self.assertFalse(
            self.service._looks_like_partial_quote("show me Einstein quotes")
        )

    def test_partial_quote_detection_for_who_said_query(self):
        self.assertFalse(
            self.service._looks_like_partial_quote("who said to be or not to be")
        )


if __name__ == "__main__":
    unittest.main()
