from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from google.genai import types
from backend.models import SearchIntent
from backend.config import log_model_event


# Gemini

logger = logging.getLogger(__name__)

_INTENT_INSTRUCTION = """Turn a Wikiquote request into a search intent. The request may be
misspelled, ungrammatical, or a rough voice transcript.

kind:
  topic           a subject, feeling, or idea
  author          every quotation by one person
  quote_fragment  wording the user half remembers and wants completed
  random          no subject at all
  repeat, alternative, attribution: only when the request points at the previous answer

search_text is matched against the text of the quotations themselves, so write the words a
matching quotation would use, not the words the user used:
  topic           corrected content words plus close synonyms; drop filler and question words
  author          the person's name
  quote_fragment  the remembered words as spoken, uncorrected

author holds a person's name when a topic request also names one, otherwise empty.

Examples:
  "i wanna know sumthing about how ur mistakes make u learn better"
    -> topic, search_text "mistakes learn failure lesson", author ""
  "wat did einstein say about imaginaton"
    -> topic, search_text "imagination knowledge", author "Einstein"
  "how does that go, life is like a box of chocolate"
    -> quote_fragment, search_text "life is like a box of chocolate", author ""

Classify the current request only. Earlier requests are there to resolve words like
"he" or "that", and a request that names its own subject is never a follow-up.

Never answer the request, never write a quotation, never write a query language."""


class GeminiService:
    def __init__(self, client: Any | None, llm_model: str):
        self.client = client
        self.llm_model = llm_model

    async def interpret(
        self, message: str, context: list[dict[str, str]]
    ) -> SearchIntent:
        started = perf_counter()
        fallback = SearchIntent(kind="topic", search_text=message.strip(), limit=5)
        if self.client is None:
            log_model_event(
                model=self.llm_model,
                intent=fallback.kind,
                latency_ms=self._elapsed_ms(started),
                fallback="missing_api_key",
            )
            return fallback

        earlier = [
            item["content"] for item in context if item["role"] == "user"
        ][-2:]
        prompt = "\n".join(
            [f"earlier request: {text}" for text in earlier]
            + [f"current request: {message}"]
        )
        try:
            response = await self.client.aio.models.generate_content(
                model=self.llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_INTENT_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=SearchIntent,
                ),
            )
            if response.parsed is None:
                log_model_event(
                    model=self.llm_model,
                    intent=fallback.kind,
                    latency_ms=self._elapsed_ms(started),
                    fallback="invalid_response",
                )
                return fallback
            intent = response.parsed
            if not intent.search_text.strip() and intent.kind not in {
                "random",
                "repeat",
                "alternative",
                "attribution",
            }:
                intent = intent.model_copy(update={"search_text": message.strip()})
            usage = getattr(response, "usage_metadata", None)
            log_model_event(
                model=self.llm_model,
                intent=intent.kind,
                latency_ms=self._elapsed_ms(started),
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
                fallback="none",
            )
            return intent
        except Exception as exc:
            logger.warning("Gemini intent extraction failed: %s", type(exc).__name__)
            log_model_event(
                model=self.llm_model,
                intent=fallback.kind,
                latency_ms=self._elapsed_ms(started),
                fallback=type(exc).__name__,
            )
            return fallback

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return round((perf_counter() - started) * 1000)
