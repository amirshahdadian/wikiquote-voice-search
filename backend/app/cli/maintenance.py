from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from backend.app.core.logging import configure_logging
from backend.app.core.settings import Settings, settings
from backend.app.integrations.gemini import GeminiService
from backend.app.integrations.neo4j_repository import Neo4jQuoteRepository

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain the Wikiquote graph")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schema", help="Create constraints and search indexes")
    commands.add_parser("embed", help="Submit or import a Gemini embedding batch")
    commands.add_parser("verify", help="Print graph node counts")
    return parser

def create_repository(app_settings: Settings) -> Neo4jQuoteRepository:
    return Neo4jQuoteRepository(
        app_settings.neo4j_uri,
        app_settings.neo4j_username,
        app_settings.neo4j_password,
    )


def create_gemini_service(app_settings: Settings) -> GeminiService:
    if app_settings.gemini_api_key is None:
        raise RuntimeError("GEMINI_API_KEY is required for the embed command")
    client = genai.Client(
        api_key=app_settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=int(app_settings.gemini_timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(
                attempts=app_settings.gemini_max_retries
            ),
        ),
    )
    return GeminiService(
        client,
        app_settings.gemini_llm_model,
        app_settings.gemini_embedding_model,
        app_settings.gemini_embedding_dimensions,
    )


def run_embedding_command(
    repository: Neo4jQuoteRepository,
    gemini_service: GeminiService,
    *,
    artifacts_dir: Path,
    model: str,
    dimensions: int,
) -> str:
    state_file = artifacts_dir / "embeddings" / "current-job.json"
    if state_file.exists():
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        if saved["model"] != model or saved["dimensions"] != dimensions:
            raise RuntimeError("Saved embedding job does not match current settings")
        state, vectors = gemini_service.read_embedding_batch(saved["job_name"])
        if state == "JOB_STATE_SUCCEEDED":
            rows = [
                {"quote_id": quote_id, "embedding": embedding}
                for quote_id, embedding in vectors.items()
            ]
            for start in range(0, len(rows), 500):
                repository.save_embeddings(
                    rows[start : start + 500],
                    model=model,
                    dimensions=dimensions,
                )
            state_file.unlink()
        elif state in {"JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}:
            raise RuntimeError(f"Gemini embedding batch ended in {state}")
        return state

    rows = repository.pending_embedding_rows(model, dimensions, 100_000)
    if not rows:
        return "CURRENT"
    job_name = gemini_service.create_embedding_batch(rows)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "job_name": job_name,
                "model": model,
                "dimensions": dimensions,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return "JOB_STATE_SUBMITTED"


def run_command(
    args: argparse.Namespace,
    app_settings: Settings = settings,
    repository: Neo4jQuoteRepository | None = None,
    gemini_service: GeminiService | None = None,
) -> dict[str, int] | None:
    graph = repository or create_repository(app_settings)
    owns_repository = repository is None
    try:
        if args.command == "schema":
            graph.ensure_schema()
            return None
        if args.command == "verify":
            return graph.verify_counts(
                app_settings.gemini_embedding_model,
                app_settings.gemini_embedding_dimensions,
            )
        if args.command == "embed":
            service = gemini_service or create_gemini_service(app_settings)
            state = run_embedding_command(
                graph,
                service,
                artifacts_dir=app_settings.artifacts_dir,
                model=app_settings.gemini_embedding_model,
                dimensions=app_settings.gemini_embedding_dimensions,
            )
            print(state)
            return None
        raise ValueError(f"Unsupported command: {args.command}")
    finally:
        if owns_repository:
            graph.close()


def main() -> None:
    configure_logging(settings.log_level)
    result = run_command(build_parser().parse_args())
    if result:
        for label, count in result.items():
            print(f"{label}: {count:,}")


if __name__ == "__main__":
    main()
