from __future__ import annotations

import argparse
import logging

from backend.config import Settings, configure_logging, settings
from backend.neo4j import Neo4jQuoteRepository


# Maintenance

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain the Wikiquote graph")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="Print graph node counts")
    return parser


def run_command(
    args: argparse.Namespace,
    app_settings: Settings = settings,
    repository: Neo4jQuoteRepository | None = None,
) -> dict[str, int] | None:
    graph = repository or Neo4jQuoteRepository(
        app_settings.neo4j_uri,
        app_settings.neo4j_username,
        app_settings.neo4j_password,
    )
    try:
        if args.command == "verify":
            return graph.verify_counts()
        raise ValueError(f"Unsupported command: {args.command}")
    finally:
        if repository is None:
            graph.close()


def main() -> None:
    configure_logging(settings.log_level)
    result = run_command(build_parser().parse_args())
    if result:
        for label, count in result.items():
            print(f"{label}: {count:,}")


if __name__ == "__main__":
    main()
