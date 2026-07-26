from __future__ import annotations

from collections import OrderedDict
from typing import Any

from backend.app.domain import QueryState


class QueryWorkflow:
    def __init__(self, gemini: Any, search: Any, max_threads: int = 1000):
        self.gemini = gemini
        self.search = search
        self.max_threads = max_threads
        self.states: OrderedDict[str, QueryState] = OrderedDict()

    async def run(self, message: str, conversation_id: str) -> QueryState:
        previous = self.states.pop(conversation_id, {})
        intent = await self.gemini.interpret(message, previous.get("history", []))
        hits = previous.get("hits", [])
        result_index = previous.get("result_index", 0)
        warnings: list[str] = []

        if intent.kind == "alternative" and hits:
            if result_index + 1 < len(hits):
                result_index += 1
            else:
                warnings.append("no_additional_matches")
        elif intent.kind not in {"repeat", "attribution"} or not hits:
            hits = await self.search.search(intent)
            result_index = 0
            if not hits:
                warnings.append("no_quote_found")

        if hits:
            selected = hits[min(result_index, len(hits) - 1)]
            author = selected.author_name or "Unknown attribution"
            if intent.kind == "attribution":
                response_text = (
                    f"That quotation is attributed to {author} "
                    f"on {selected.page_title}."
                )
            else:
                response_text = f'"{selected.quote_text}" — {author}'
        else:
            response_text = (
                f'I could not find a reliable match for "{intent.search_text}".'
            )

        state: QueryState = {
            "message": message,
            "conversation_id": conversation_id,
            "intent": intent,
            "hits": hits,
            "result_index": result_index,
            "response_text": response_text,
            "warnings": warnings,
            "history": [
                *previous.get("history", []),
                {"role": "user", "content": message},
                {"role": "assistant", "content": response_text},
            ][-8:],
        }
        self.states[conversation_id] = state
        while len(self.states) > self.max_threads:
            self.states.popitem(last=False)
        return state


def build_query_workflow(
    gemini: Any,
    search: Any,
    *,
    max_threads: int = 1000,
) -> QueryWorkflow:
    return QueryWorkflow(gemini, search, max_threads)
