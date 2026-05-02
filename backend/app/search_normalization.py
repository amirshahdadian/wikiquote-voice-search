"""Shared helpers for quote-search text normalization."""
from __future__ import annotations

import re
import unicodedata

APOSTROPHE_CHARS = "'\u2019\u2018\u02bc\u0060\u00b4\u201b"
CONTRACTION_SUFFIXES = ("ll", "re", "ve", "d", "m", "s", "t")
CONTRACTION_BASES = {
    "ain",
    "are",
    "can",
    "couldn",
    "didn",
    "doesn",
    "do",
    "don",
    "hadn",
    "hasn",
    "haven",
    "he",
    "here",
    "how",
    "i",
    "isn",
    "it",
    "let",
    "mustn",
    "she",
    "shouldn",
    "that",
    "there",
    "they",
    "wasn",
    "we",
    "weren",
    "what",
    "where",
    "who",
    "wo",
    "wouldn",
    "you",
}


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_search_text(text: str) -> str:
    """Normalize text for punctuation-insensitive quote matching."""
    normalized = _strip_diacritics(text)
    for char in APOSTROPHE_CHARS:
        normalized = normalized.replace(char, "'")
    normalized = normalized.lower().replace("&", " and ")
    normalized = re.sub(r"(?<=[a-z0-9])'+(?=[a-z0-9])", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def legacy_normalize_search_text(text: str) -> str:
    """Preserve the historical normalization form used in older DB rows."""
    normalized = _strip_diacritics(text)
    normalized = normalized.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def build_legacy_contraction_variant(normalized_text: str) -> str:
    """Approximate legacy apostrophe splitting for contraction-like tokens."""
    tokens: list[str] = []
    changed = False

    for token in normalized_text.split():
        replacement = token
        for suffix in CONTRACTION_SUFFIXES:
            if not token.endswith(suffix) or len(token) <= len(suffix) + 1:
                continue
            base = token[: -len(suffix)]
            if base not in CONTRACTION_BASES:
                continue
            replacement = f"{base} {suffix}"
            changed = True
            break
        tokens.append(replacement)

    if not changed:
        return normalized_text
    return " ".join(" ".join(tokens).split())


def search_text_variants(text: str) -> list[str]:
    """Return canonical plus legacy-compatible normalized variants."""
    variants: list[str] = []
    for candidate in (
        normalize_search_text(text),
        legacy_normalize_search_text(text),
        build_legacy_contraction_variant(normalize_search_text(text)),
    ):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants
