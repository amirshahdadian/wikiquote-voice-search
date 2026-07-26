from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.app.domain import QueryState


def build_query_workflow(gemini: Any, search: Any):
    async def interpret(state: QueryState) -> QueryState:
        intent = await gemini.interpret(
            state["message"],
            state.get("history", []),
        )
        return {"intent": intent, "warnings": []}

    async def retrieve(state: QueryState) -> QueryState:
        intent = state["intent"]
        previous = state.get("hits", [])
        current_index = state.get("result_index", 0)
        if intent.kind in {"repeat", "attribution"} and previous:
            return {"result_index": current_index}
        if intent.kind == "alternative" and previous:
            next_index = current_index + 1
            if next_index < len(previous):
                return {"result_index": next_index}
            return {
                "result_index": current_index,
                "warnings": ["no_additional_matches"],
            }
        hits = await search.search(intent)
        return {
            "hits": hits,
            "result_index": 0,
            "warnings": [] if hits else ["no_quote_found"],
        }

    def respond(state: QueryState) -> QueryState:
        hits = state.get("hits", [])
        intent = state["intent"]
        if not hits:
            response_text = (
                f'I could not find a reliable match for "{intent.search_text}".'
            )
        else:
            index = min(state.get("result_index", 0), len(hits) - 1)
            selected = hits[index]
            author = selected.author_name or "Unknown attribution"
            if intent.kind == "attribution":
                response_text = (
                    f"That quotation is attributed to {author} "
                    f"on {selected.page_title}."
                )
            else:
                response_text = f'"{selected.quote_text}" — {author}'

        history = [
            *state.get("history", []),
            {"role": "user", "content": state["message"]},
            {"role": "assistant", "content": response_text},
        ][-8:]
        return {"response_text": response_text, "history": history}

    builder = StateGraph(QueryState)
    builder.add_node("interpret", interpret)
    builder.add_node("retrieve", retrieve)
    builder.add_node("respond", respond)
    builder.add_edge(START, "interpret")
    builder.add_edge("interpret", "retrieve")
    builder.add_edge("retrieve", "respond")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=InMemorySaver())
