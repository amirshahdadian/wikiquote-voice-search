#!/usr/bin/env python3
"""Run a quote-autocomplete demo and synthesize the best match to audio."""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services.tts_service import TTSService
from src.wikiquote_voice.config import Config
from src.wikiquote_voice.search.service import QuoteSearchService


def run_demo() -> None:
    print("=" * 70)
    print("Autocomplete with text-to-speech demo")
    print("=" * 70)

    search_service = QuoteSearchService(
        Config.NEO4J_URI,
        Config.NEO4J_USERNAME,
        Config.NEO4J_PASSWORD,
    )

    try:
        search_service.connect()
        print("Connected to Neo4j")
        search_service.build_semantic_index(sample_size=5000)

        print("Loading TTS")
        tts_service = TTSService(device="cpu")

        test_queries = [
            "to be or not",
            "imagination is more",
            "the only thing we have",
            "in the end",
            "all you need is",
        ]

        for index, query in enumerate(test_queries, start=1):
            print("-" * 70)
            print(f"Query {index}: {query}")
            results = search_service.search_quotes(query, limit=1)

            if not results:
                print("No match found")
                continue

            top_match = results[0]
            quote_text = top_match["quote_text"]
            author_name = top_match["author_name"]
            print(f"Quote: {quote_text}")
            print(f"Author: {author_name}")
            print(f"Search type: {top_match.get('search_type', 'unknown')}")

            speech_text = f'"{quote_text}" by {author_name}'
            output_file = ROOT / f"autocomplete_demo_{index}.wav"
            try:
                tts_service.synthesize_personalized(
                    text=speech_text,
                    output_path=str(output_file),
                    preferences={
                        "pitch_scale": 1.0,
                        "speaking_rate": 0.9,
                        "energy_scale": 1.0,
                        "style": "neutral",
                    },
                )
                print(f"Saved audio to {output_file.name}")
            except Exception as exc:
                print(f"TTS failed: {exc}")

            time.sleep(0.5)
    finally:
        search_service.close()


def print_usage_example() -> None:
    print(
        """
from src.wikiquote_voice.search.service import QuoteSearchService
from services.tts_service import TTSService

search = QuoteSearchService(uri, username, password)
tts = TTSService(device="cpu")

results = search.search_quotes("to be or not", limit=1)
if results:
    top_match = results[0]
    speech_text = f'"{top_match["quote_text"]}" by {top_match["author_name"]}'
    tts.synthesize_personalized(text=speech_text, output_path="autocomplete.wav")
""".strip()
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autocomplete + TTS demo")
    parser.add_argument("--demo", action="store_true", help="Print a minimal code sample")
    args = parser.parse_args()

    if args.demo:
        print_usage_example()
    else:
        run_demo()
