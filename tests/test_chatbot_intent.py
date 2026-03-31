import unittest

from services.chatbot_service import ChatbotService


class ChatbotIntentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChatbotService.__new__(ChatbotService)

    def test_extract_intent_for_quote_lookup(self):
        intent = self.service.extract_intent("who said to be or not to be?")
        self.assertEqual(
            intent,
            {
                "type": "topic_search",
                "query": "to be or not to be",
                "limit": 5,
            },
        )

    def test_extract_intent_for_topic_search(self):
        intent = self.service.extract_intent("quotes about courage and fear")
        self.assertEqual(
            intent,
            {
                "type": "topic_search",
                "query": "courage and fear",
                "limit": 5,
            },
        )

    def test_extract_intent_for_author_search(self):
        intent = self.service.extract_intent("Einstein quotes")
        self.assertEqual(
            intent,
            {
                "type": "author_search",
                "author": "Einstein",
                "limit": 5,
            },
        )


if __name__ == "__main__":
    unittest.main()
