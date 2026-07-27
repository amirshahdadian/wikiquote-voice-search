"""Extract structurally marked quotations from a Wikiquote XML dump."""
from __future__ import annotations

import hashlib
import html
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import mwparserfromhell

from backend.app.core.logging import configure_logging
from backend.app.core.settings import settings
from backend.app.integrations.neo4j_repository import Neo4jQuoteRepository

logger = logging.getLogger(__name__)

QUOTE_TEMPLATES = {
    "quote",
    "cquote",
    "quotation",
    "bquote",
    "rquote",
    "quote box",
    "pull quote",
}
EXCLUDED_SECTIONS = {
    "bibliography",
    "external links",
    "further reading",
    "misattributed",
    "references",
    "see also",
    "sources",
}
EXCLUDED_NAMESPACES = {
    "category",
    "file",
    "help",
    "media",
    "mediawiki",
    "portal",
    "template",
    "user",
    "wikiquote",
}


@dataclass(slots=True)
class ExtractedQuote:
    quote: str
    author: str | None
    page_title: str
    page_type: str
    work: str | None = None
    citation: str | None = None
    quote_type: str = "sourced"
    page_id: int | None = None
    quote_id: str | None = None
    attribution_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        values = {
            "quote": self.quote,
            "author": self.author,
            "work": self.work,
            "citation": self.citation,
            "page_title": self.page_title,
            "quote_type": self.quote_type,
            "quote_id": self.quote_id,
            "attribution_id": self.attribution_id,
        }
        return {key: value for key, value in values.items() if value is not None}

@dataclass(frozen=True, slots=True)
class PageMetadata:
    title: str
    page_type: str
    default_author: str | None
    default_work: str | None


def stable_id(*parts: object) -> str:
    value = "\x1f".join(
        "" if part is None else str(part).strip().casefold() for part in parts
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class MWParserQuoteExtractor:
    """A small extractor that trusts Wikiquote structure instead of guessing."""

    def __init__(self):
        self.seen_attributions: set[str] = set()
        self.processed_pages = 0
        self.total_quotes = 0
        self.min_length = settings.quote_min_length
        self.max_length = settings.quote_max_length
        self.min_words = settings.quote_min_words
        self.max_words = settings.quote_max_words
        self.min_alpha_ratio = settings.quote_min_alpha_ratio

    def extract_page(
        self,
        title: str,
        page_id: int,
        wikitext: str,
    ) -> list[ExtractedQuote]:
        if not self._should_process_page(title, wikitext):
            return []

        metadata = self._classify_page(title, wikitext)
        raw_quotes = [
            *self._extract_templates(wikitext, metadata),
            *self._extract_blockquotes(wikitext, metadata),
            *self._extract_bullets(wikitext, metadata),
        ]
        rows: list[ExtractedQuote] = []
        for raw_quote in raw_quotes:
            raw_quote.page_id = page_id
            quote = self._finalize_quote(raw_quote)
            if quote.attribution_id in self.seen_attributions:
                continue
            self.seen_attributions.add(quote.attribution_id)
            rows.append(quote)
        self.total_quotes += len(rows)
        return rows

    def iter_wikiquote_xml(
        self, xml_file_path: str, limit: int | None = None
    ) -> Iterator[dict[str, Any]]:
        for _, element in ET.iterparse(xml_file_path, events=("end",)):
            if self._local_name(element.tag) != "page":
                continue
            title = self._child_text(element, "title")
            page_id = self._direct_child_int(element, "id")
            revision = self._direct_child(element, "revision")
            text = self._child_text(revision, "text") if revision is not None else ""
            if title and page_id is not None:
                extracted = self.extract_page(title, page_id, text)
                yield from (item.to_dict() for item in extracted)
                self.processed_pages += 1
            element.clear()
            if limit is not None and self.processed_pages >= limit:
                break

    def _extract_templates(
        self, wikitext: str, metadata: PageMetadata
    ) -> list[ExtractedQuote]:
        results: list[ExtractedQuote] = []
        wikicode = mwparserfromhell.parse(wikitext)
        for template in wikicode.filter_templates(recursive=True):
            name = self._clean(str(template.name)).casefold()
            if name not in QUOTE_TEMPLATES:
                continue
            parameters = {
                str(parameter.name).strip().casefold(): str(parameter.value)
                for parameter in template.params
            }
            quote = self._first(
                parameters, "text", "quote", "content", "1"
            )
            author = self._first(parameters, "author", "by", "speaker", "2")
            work = self._first(parameters, "source", "work", "title", "3")
            quote_text = self._clean(quote)
            if not self._is_valid_quote(quote_text):
                continue
            author_text = self._clean(author) or metadata.default_author
            work_text = self._clean(work) or metadata.default_work
            if metadata.page_type == "theme" and not author_text:
                continue
            results.append(
                ExtractedQuote(
                    quote=quote_text,
                    author=author_text,
                    work=work_text,
                    citation=self._clean(work) or None,
                    page_title=metadata.title,
                    page_type=metadata.page_type,
                )
            )
        return results

    def _extract_blockquotes(
        self, wikitext: str, metadata: PageMetadata
    ) -> list[ExtractedQuote]:
        results: list[ExtractedQuote] = []
        pattern = re.compile(
            r"<blockquote(?:\s[^>]*)?>(.*?)</blockquote>",
            re.IGNORECASE | re.DOTALL,
        )
        for match in pattern.finditer(wikitext):
            quote = self._clean(match.group(1))
            if not self._is_valid_quote(quote):
                continue
            if metadata.page_type == "theme" and not metadata.default_author:
                continue
            results.append(
                ExtractedQuote(
                    quote=quote,
                    author=metadata.default_author,
                    work=metadata.default_work,
                    page_title=metadata.title,
                    page_type=metadata.page_type,
                )
            )
        return results

    def _extract_bullets(
        self, wikitext: str, metadata: PageMetadata
    ) -> list[ExtractedQuote]:
        results: list[ExtractedQuote] = []
        pending: ExtractedQuote | None = None
        section = ""

        def flush() -> None:
            nonlocal pending
            if pending and (
                metadata.page_type != "theme" or pending.author is not None
            ):
                results.append(pending)
            pending = None

        for raw_line in wikitext.splitlines():
            heading = re.match(r"^={2,6}\s*(.*?)\s*={2,6}\s*$", raw_line.strip())
            if heading:
                flush()
                section = self._clean(heading.group(1))
                continue
            if self._is_excluded_section(section):
                continue

            attribution = re.match(r"^\*{2,}\s*(.+)$", raw_line.strip())
            if attribution and pending:
                citation = attribution.group(1)
                infer_author = (
                    metadata.page_type == "theme"
                    or pending.quote_type == "about"
                    or (
                        metadata.page_type == "literary_work"
                        and bool(re.search(r"''+\s*\[\[", citation))
                    )
                )
                author, work = self._parse_attribution(
                    citation,
                    infer_author=infer_author,
                )
                pending.author = author or pending.author
                pending.work = work or pending.work
                pending.citation = self._clean(citation)
                continue

            bullet = re.match(r"^[*#]\s+(.+)$", raw_line.strip())
            if not bullet:
                continue
            flush()
            quote = self._clean(bullet.group(1))
            if not self._is_valid_quote(quote):
                continue
            pending = ExtractedQuote(
                quote=quote,
                author=metadata.default_author,
                work=metadata.default_work,
                page_title=metadata.title,
                page_type=metadata.page_type,
                quote_type=self._quote_type(section),
            )
        flush()
        return results

    def _parse_attribution(
        self,
        text: str,
        *,
        infer_author: bool = True,
    ) -> tuple[str | None, str | None]:
        italic_links = [
            self._link_text(match)
            for match in re.findall(
                r"''+\s*\[\[([^\]]+)\]\]\s*''+", text
            )
        ]
        links = [
            self._link_text(match)
            for match in re.findall(r"\[\[([^\]]+)\]\]", text)
        ]
        author = (
            next((link for link in links if link not in italic_links), None)
            if infer_author
            else None
        )
        work = italic_links[0] if italic_links else None

        template_author = re.search(
            r"(?:^|\|)\s*author\d*\s*=\s*([^|]+)", text, re.IGNORECASE
        )
        template_title = re.search(
            r"(?:^|\|)\s*title\s*=\s*([^|]+)", text, re.IGNORECASE
        )
        if template_author:
            author = self._clean(template_author.group(1))
        if template_title:
            work = self._clean(template_title.group(1))

        return author or None, work or None

    def _finalize_quote(self, quote: ExtractedQuote) -> ExtractedQuote:
        quote.quote = self._clean(quote.quote)
        quote.author = self._clean(quote.author) or None
        quote.work = self._clean(quote.work) or None
        quote.citation = self._clean(quote.citation) or None
        quote.quote_id = stable_id(self._normalize(quote.quote))
        quote.attribution_id = stable_id(
            quote.quote_id,
            quote.page_id,
            quote.author,
            quote.work,
            quote.quote_type,
            quote.citation,
        )
        return quote

    def _classify_page(self, title: str, wikitext: str) -> PageMetadata:
        categories = {
            self._clean(category.title)
            for category in mwparserfromhell.parse(wikitext).filter_wikilinks()
            if str(category.title).casefold().startswith("category:")
        }
        category_text = " ".join(categories).casefold()
        if "film" in category_text:
            return PageMetadata(title, "film", None, title)
        work_category = re.search(
            r"\b(?:books?|novels?|plays?|tragedy|tragedies|comedy|comedies|"
            r"literary works?|poems?|works by)\b",
            category_text,
        )
        if work_category:
            return PageMetadata(title, "literary_work", None, title)
        dated_person = re.search(
            r"\b(?:1\d{3}|20\d{2}) (?:births|deaths)\b",
            category_text,
        )
        has_sort_name = re.search(
            r"\{\{\s*defaultsort\s*:",
            wikitext,
            re.IGNORECASE,
        )
        if dated_person or has_sort_name or any(
            label in category_text for label in ("people", "persons")
        ):
            return PageMetadata(title, "person", title, None)
        return PageMetadata(title, "theme", None, None)

    def _should_process_page(self, title: str, content: str) -> bool:
        if not title or not content.strip():
            return False
        if ":" in title and title.split(":", 1)[0].casefold() in EXCLUDED_NAMESPACES:
            return False
        return not content.lstrip().casefold().startswith("#redirect")

    def _is_excluded_section(self, title: str) -> bool:
        normalized = title.casefold().strip()
        return any(
            normalized == excluded or normalized.startswith(f"{excluded} ")
            for excluded in EXCLUDED_SECTIONS
        )

    def _is_valid_quote(self, text: str) -> bool:
        if not text or len(text) < self.min_length or len(text) > self.max_length:
            return False
        words = text.split()
        if len(words) < self.min_words or len(words) > self.max_words:
            return False
        alpha_ratio = sum(character.isalpha() for character in text) / len(text)
        return alpha_ratio >= self.min_alpha_ratio

    @staticmethod
    def _quote_type(section: str) -> str:
        lowered = section.casefold()
        if "misattributed" in lowered or "disputed" in lowered:
            return "disputed"
        if "attributed" in lowered:
            return "attributed"
        if "about" in lowered:
            return "about"
        return "sourced"

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        return " ".join(normalized.split())

    @staticmethod
    def _clean(value: Any) -> str:
        if value is None:
            return ""
        raw = re.sub(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", " ", str(value), flags=re.I | re.S)
        try:
            raw = mwparserfromhell.parse(raw).strip_code(
                normalize=True, collapse=True
            )
        except Exception:
            pass
        return " ".join(html.unescape(raw).replace("\xa0", " ").split()).strip()

    @staticmethod
    def _link_text(value: str) -> str:
        target, _, display = value.partition("|")
        result = display or target
        if ":" in result and result.split(":", 1)[0].casefold() in {
            "q",
            "w",
            "wikipedia",
            "wikiquote",
        }:
            result = result.split(":", 1)[1]
        return result.split("#", 1)[0].strip()

    @staticmethod
    def _first(parameters: dict[str, str], *names: str) -> str | None:
        return next(
            (parameters[name] for name in names if parameters.get(name)),
            None,
        )

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @classmethod
    def _direct_child(cls, element: ET.Element | None, name: str):
        if element is None:
            return None
        return next(
            (
                child
                for child in element
                if cls._local_name(child.tag) == name
            ),
            None,
        )

    @classmethod
    def _child_text(cls, element: ET.Element | None, name: str) -> str:
        child = cls._direct_child(element, name)
        return child.text or "" if child is not None else ""

    @classmethod
    def _direct_child_int(
        cls, element: ET.Element | None, name: str
    ) -> int | None:
        value = cls._child_text(element, name)
        return int(value) if value.strip().isdigit() else None

def main() -> None:
    configure_logging(settings.log_level)
    extractor = MWParserQuoteExtractor()
    repository = Neo4jQuoteRepository(
        settings.neo4j_uri,
        settings.neo4j_username,
        settings.neo4j_password,
    )
    try:
        repository.ensure_schema()
        repository.load(
            extractor.iter_wikiquote_xml(
                str(settings.xml_file),
                limit=settings.parse_page_limit,
            ),
            batch_size=settings.batch_size,
        )
    finally:
        repository.close()
    logger.info(
        "Extracted %d quotations from %d pages",
        extractor.total_quotes,
        extractor.processed_pages,
    )


if __name__ == "__main__":
    main()
