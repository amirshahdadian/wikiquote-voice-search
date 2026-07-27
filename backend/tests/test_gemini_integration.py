import asyncio
from types import SimpleNamespace

from backend.models import SearchIntent
from backend.gemini import GeminiService, _INTENT_INSTRUCTION


class FakeModels:
    def __init__(self, intent=None):
        self.last_contents = None
        self.last_config = None
        self.intent = intent or SearchIntent(
            kind="author", search_text="Virginia Woolf", limit=5
        )

    async def generate_content(self, **kwargs):
        self.last_contents = kwargs["contents"]
        self.last_config = kwargs["config"]
        return SimpleNamespace(parsed=self.intent)


class FakeClient:
    def __init__(self, intent=None):
        self.models = FakeModels(intent)
        self.aio = SimpleNamespace(models=self.models)


def service(client) -> GeminiService:
    return GeminiService(client, "gemini-3.5-flash-lite")


def test_interpret_returns_validated_schema():
    client = FakeClient()

    intent = asyncio.run(
        service(client).interpret(
            "quotes by Virginia Woolf",
            [
                {"role": "user", "content": "find something about courage"},
                {
                    "role": "assistant",
                    "content": "A quotation that should stay out of the intent prompt",
                },
            ],
        )
    )

    assert intent.kind == "author"
    assert intent.search_text == "Virginia Woolf"
    assert "find something about courage" in client.models.last_contents
    assert "A quotation that should stay out" not in client.models.last_contents


def test_the_current_request_is_labelled_apart_from_earlier_ones():
    client = FakeClient()

    asyncio.run(
        service(client).interpret(
            "something about the sea",
            [
                {"role": "user", "content": "who said that?"},
                {"role": "user", "content": "repeat that"},
            ],
        )
    )

    prompt = client.models.last_contents
    assert prompt.splitlines() == [
        "earlier request: who said that?",
        "earlier request: repeat that",
        "current request: something about the sea",
    ]
    assert "Classify the current request only" in _INTENT_INSTRUCTION


def test_interpret_carries_the_rewrite_instruction_and_typed_schema():
    client = FakeClient()

    asyncio.run(service(client).interpret("courage", []))

    assert client.models.last_config.response_schema is SearchIntent
    assert "search_text is matched against the text of the quotations" in (
        _INTENT_INSTRUCTION
    )
    assert "never write a query language" in _INTENT_INSTRUCTION


def test_a_named_person_in_a_topic_request_survives_as_a_filter():
    client = FakeClient(
        SearchIntent(kind="topic", search_text="imagination knowledge", author="Einstein")
    )

    intent = asyncio.run(service(client).interpret("wat did einstein say about imaginaton", []))

    assert intent.author == "Einstein"
    assert intent.search_text == "imagination knowledge"


def test_an_empty_rewrite_falls_back_to_the_original_request():
    client = FakeClient(SearchIntent(kind="topic", search_text="   "))

    intent = asyncio.run(service(client).interpret("hope in difficult times", []))

    assert intent.search_text == "hope in difficult times"


def test_missing_client_falls_back_to_topic_intent():
    intent = asyncio.run(service(None).interpret("hope in difficult times", []))

    assert intent == SearchIntent(
        kind="topic", search_text="hope in difficult times", limit=5
    )
