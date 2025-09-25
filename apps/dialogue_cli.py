"""Command-line interface for the Wikiquote dialogue experience."""
from __future__ import annotations

import argparse
import logging
from typing import Optional

from wikiquote_voice import Config
from wikiquote_voice.dialogue import DialogueManager, GraphSearchAdapter
from wikiquote_voice.search import QuoteSearchService


def build_manager(style: Optional[str], limit: Optional[int]) -> DialogueManager:
    """Construct a dialogue manager wired up to the graph search service."""

    search_service = QuoteSearchService(
        Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD
    )
    adapter = GraphSearchAdapter(search_service)
    manager = DialogueManager(adapter, search_limit=limit or Config.SEARCH_LIMIT)
    if style:
        manager.set_user_style(style)
    return manager


def main() -> None:
    parser = argparse.ArgumentParser(description="Wikiquote dialogue demo")
    parser.add_argument(
        "--style",
        choices=["neutral", "friendly", "formal", "enthusiastic", "concise"],
        default="neutral",
        help="Response style to use for generated replies.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=Config.SEARCH_LIMIT,
        help="Maximum number of quotes to request from each search.",
    )
    parser.add_argument(
        "--log-level",
        default=Config.LOG_LEVEL,
        help="Logging level for debugging (default comes from configuration).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    manager = build_manager(args.style, args.limit)

    print("Wikiquote dialogue agent ready. Type 'exit' to quit.\n")

    try:
        while True:
            try:
                user_input = input("You: ")
            except EOFError:
                print()
                break

            if user_input is None:
                continue

            utterance = user_input.strip()
            if not utterance:
                continue

            if utterance.lower() in {"exit", "quit", "bye"}:
                break

            response = manager.handle_utterance(utterance)
            print(f"Assistant: {response}")
    except KeyboardInterrupt:
        print()
    finally:
        manager.close()
        print("Goodbye!")


if __name__ == "__main__":
    main()
