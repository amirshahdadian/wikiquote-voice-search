import asyncio

from backend.models import QuoteHit, SearchIntent
from backend.search import QueryWorkflow


class FakeGemini:
    async def interpret(self, message, context):
        lowered = message.lower()
        if "who said" in lowered:
            return SearchIntent(kind="attribution")
        if "another" in lowered:
            return SearchIntent(kind="alternative")
        if "repeat" in lowered:
            return SearchIntent(kind="repeat")
        return SearchIntent(kind="topic", search_text="courage")


class FakeSearch:
    async def search(self, intent):
        return [
            QuoteHit(
                quote_id="q1",
                quote_text="Courage is grace under pressure.",
                author_name="Ernest Hemingway",
                page_title="Ernest Hemingway",
                relevance_score=1.0,
                search_type="lexical",
            ),
            QuoteHit(
                quote_id="q2",
                quote_text="Courage starts with showing up.",
                author_name="Brené Brown",
                page_title="Brené Brown",
                relevance_score=0.9,
                search_type="lexical",
            ),
        ]


def test_topic_query_runs_interpret_retrieve_respond():
    workflow = QueryWorkflow(FakeGemini(), FakeSearch())

    result = asyncio.run(
        workflow.run("something about courage", "c1")
    )

    assert result["intent"].kind == "topic"
    assert result["hits"][0].quote_text == "Courage is grace under pressure."
    assert result["response_text"] == (
        '"Courage is grace under pressure." — Ernest Hemingway'
    )


def test_attribution_followup_uses_previous_hit():
    workflow = QueryWorkflow(FakeGemini(), FakeSearch())

    async def scenario():
        await workflow.run("something about courage", "c1")
        return await workflow.run("who said that?", "c1")

    result = asyncio.run(scenario())

    assert result["intent"].kind == "attribution"
    assert result["result_index"] == 0
    assert result["response_text"] == (
        "That quotation is attributed to Ernest Hemingway on Ernest Hemingway."
    )


def test_alternative_advances_without_requerying():
    search = FakeSearch()
    search.calls = 0
    original_search = search.search

    async def counted_search(intent):
        search.calls += 1
        return await original_search(intent)

    search.search = counted_search
    workflow = QueryWorkflow(FakeGemini(), search)

    async def scenario():
        await workflow.run("something about courage", "c1")
        return await workflow.run("another one", "c1")

    result = asyncio.run(scenario())

    assert search.calls == 1
    assert result["result_index"] == 1
    assert result["hits"][1].quote_id == "q2"


def test_empty_search_result_is_explicit():
    class EmptySearch:
        async def search(self, intent):
            return []

    workflow = QueryWorkflow(FakeGemini(), EmptySearch())

    result = asyncio.run(
        workflow.run("something obscure", "c1")
    )

    assert result["warnings"] == ["no_quote_found"]
    assert result["response_text"] == (
        'I could not find a reliable match for "something obscure".'
    )


def test_conversation_memory_evicts_the_oldest_conversation():
    workflow = QueryWorkflow(FakeGemini(), FakeSearch(), max_threads=2)

    async def scenario():
        for thread_id in ("oldest", "middle", "newest"):
            await workflow.run("something about courage", thread_id)

    asyncio.run(scenario())

    assert set(workflow.states) == {"middle", "newest"}


def test_one_long_conversation_keeps_only_latest_bounded_state():
    workflow = QueryWorkflow(FakeGemini(), FakeSearch(), max_threads=2)

    async def scenario():
        for turn in range(50):
            await workflow.run(f"something about courage {turn}", "same-thread")

    asyncio.run(scenario())

    assert list(workflow.states) == ["same-thread"]
    assert len(workflow.states["same-thread"]["history"]) == 8
