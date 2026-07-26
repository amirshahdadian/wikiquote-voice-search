from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from backend.app.core.logging import configure_logging
from backend.app.core.settings import Settings, settings
from backend.app.integrations.neo4j_repository import Neo4jQuoteRepository

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain the Wikiquote graph")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schema", help="Create constraints and search indexes")
    load = commands.add_parser("load", help="Load extracted quotes")
    load.add_argument("--allow-legacy-database", action="store_true")
    commands.add_parser("verify", help="Print graph node counts")
    return parser


def load_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        raise ValueError("Extracted quotes file must contain a JSON array")
    yield from rows


def create_repository(app_settings: Settings) -> Neo4jQuoteRepository:
    return Neo4jQuoteRepository(
        app_settings.neo4j_uri,
        app_settings.neo4j_username,
        app_settings.neo4j_password,
    )


def run_command(
    args: argparse.Namespace,
    app_settings: Settings = settings,
    repository: Neo4jQuoteRepository | None = None,
) -> dict[str, int] | None:
    graph = repository or create_repository(app_settings)
    owns_repository = repository is None
    try:
        if args.command == "schema":
            graph.ensure_schema()
            return None
        if args.command == "load":
            if graph.has_legacy_schema() and not args.allow_legacy_database:
                raise RuntimeError(
                    "Legacy QuoteOccurrence/Source nodes found; load into an empty database"
                )
            graph.ensure_schema()
            graph.load(
                load_rows(app_settings.resolved_quotes_file),
                batch_size=app_settings.batch_size,
            )
            return None
        if args.command == "verify":
            return graph.verify_counts()
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
