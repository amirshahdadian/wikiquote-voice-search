from __future__ import annotations

import logging
import json
import os
import tempfile
from typing import Any

from google.genai import types

from backend.app.domain import SearchIntent

logger = logging.getLogger(__name__)

_INTENT_INSTRUCTION = """Classify a Wikiquote search request.
Return only the supplied schema.
Use topic for concepts, author for a person's quotes, quote_fragment for remembered wording,
random for an unfiltered quote, repeat/alternative/attribution only when the request refers
to a previous result. Preserve names and quotation fragments in search_text. Never answer
the request and never write Cypher."""


class GeminiUnavailable(RuntimeError):
    pass


def prepare_query(text: str) -> str:
    return f"task: search result | query: {text.strip()}"


def prepare_document(text: str) -> str:
    return f"title: none | text: {text.strip()}"


class GeminiService:
    def __init__(
        self,
        client: Any | None,
        llm_model: str,
        embedding_model: str,
        embedding_dimensions: int,
    ):
        self.client = client
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions

    async def interpret(
        self, message: str, context: list[dict[str, str]]
    ) -> SearchIntent:
        fallback = SearchIntent(kind="topic", search_text=message.strip(), limit=5)
        if self.client is None:
            return fallback

        recent_context = context[-4:]
        prompt = "\n".join(
            [f'{item["role"]}: {item["content"]}' for item in recent_context]
            + [f"user: {message}"]
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
                return fallback
            if isinstance(response.parsed, SearchIntent):
                return response.parsed
            return SearchIntent.model_validate(response.parsed)
        except Exception as exc:
            logger.warning("Gemini intent extraction failed: %s", type(exc).__name__)
            return fallback

    async def embed_query(self, text: str) -> list[float]:
        if self.client is None:
            raise GeminiUnavailable("Gemini API key is not configured")
        try:
            response = await self.client.aio.models.embed_content(
                model=self.embedding_model,
                contents=prepare_query(text),
                config=types.EmbedContentConfig(
                    output_dimensionality=self.embedding_dimensions
                ),
            )
            values = list(response.embeddings[0].values)
        except Exception as exc:
            raise GeminiUnavailable("Gemini query embedding failed") from exc
        if len(values) != self.embedding_dimensions:
            raise GeminiUnavailable(
                f"Expected {self.embedding_dimensions} embedding values, got {len(values)}"
            )
        return values

    def create_embedding_batch(self, records: list[dict[str, str]]) -> str:
        if self.client is None:
            raise GeminiUnavailable("Gemini API key is not configured")
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".jsonl", encoding="utf-8", delete=False
            ) as handle:
                temporary_path = handle.name
                for record in records:
                    request = {
                        "key": record["quote_id"],
                        "request": {
                            "content": {
                                "parts": [
                                    {"text": prepare_document(record["quote_text"])}
                                ]
                            },
                            "output_dimensionality": self.embedding_dimensions,
                        },
                    }
                    handle.write(json.dumps(request, ensure_ascii=False) + "\n")
            uploaded = self.client.files.upload(
                file=temporary_path,
                config=types.UploadFileConfig(
                    display_name="wikiquote-embedding-input",
                    mime_type="application/jsonl",
                ),
            )
            job = self.client.batches.create_embeddings(
                model=self.embedding_model,
                src={"file_name": uploaded.name},
                config={"display_name": f"wikiquote-{self.embedding_dimensions}"},
            )
        except Exception as exc:
            raise GeminiUnavailable("Could not create Gemini embedding batch") from exc
        finally:
            if temporary_path:
                os.unlink(temporary_path)
        if not job.name:
            raise GeminiUnavailable("Gemini embedding batch returned no job name")
        return job.name

    def read_embedding_batch(
        self, job_name: str
    ) -> tuple[str, dict[str, list[float]]]:
        if self.client is None:
            raise GeminiUnavailable("Gemini API key is not configured")
        try:
            job = self.client.batches.get(name=job_name)
            state = getattr(job.state, "value", job.state)
            state = str(state)
            if state != "JOB_STATE_SUCCEEDED":
                return state, {}
            file_name = getattr(job.dest, "file_name", None)
            if not file_name:
                raise GeminiUnavailable("Embedding batch has no output file")
            payload = self.client.files.download(file=file_name).decode("utf-8")
        except GeminiUnavailable:
            raise
        except Exception as exc:
            raise GeminiUnavailable("Could not read Gemini embedding batch") from exc

        records: dict[str, list[float]] = {}
        for raw_line in payload.splitlines():
            if not raw_line.strip():
                continue
            line = json.loads(raw_line)
            if line.get("error"):
                raise GeminiUnavailable(f'Embedding failed for {line.get("key", "row")}')
            response = line.get("response", {})
            embedding = response.get("embedding")
            if embedding is None:
                embeddings = response.get("embeddings") or []
                embedding = embeddings[0] if embeddings else {}
            values = list(embedding.get("values") or [])
            if len(values) != self.embedding_dimensions:
                raise GeminiUnavailable(
                    f'Invalid embedding length for {line.get("key", "row")}'
                )
            records[str(line["key"])] = values
        return state, records
