"""
Wikiquote XML Parser with mwparserfromhell

This module extracts quotes from Wikiquote XML dumps using the mwparserfromhell library.
It handles various wikitext patterns including:
- Bullet-point quotes (*, #)
- Template-based quotes ({{quote}}, {{cquote}}, {{quotation}})
- Blockquotes (<blockquote>)
- Colon-prefixed quotes (:)
- Attribution parsing (dash patterns, sub-bullets, citation templates)

The output is suitable for populating a Neo4j graph database with Author, Quote, and Source nodes.
"""

import xml.etree.ElementTree as ET
import mwparserfromhell
import json
import re
import logging
import hashlib
import unicodedata
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass, asdict

from backend.app.core.logging import configure_logging
from backend.app.core.settings import settings
from backend.app.search_normalization import normalize_search_text

logger = logging.getLogger(__name__)


@dataclass
class ExtractedQuote:
    """Structured quote data with optional metadata."""
    quote: str
    author: str
    page_title: str
    page_type: str
    source: Optional[str] = None
    work: Optional[str] = None
    source_locator: Optional[str] = None
    citation: Optional[str] = None
    speaker: Optional[str] = None
    year: Optional[str] = None
    original_text: Optional[str] = None  # For foreign language quotes
    context: Optional[str] = None  # Section context (e.g., "1930s", "Interview")
    quote_type: str = "sourced"  # sourced, attributed, disputed, about
    canonical_quote: Optional[str] = None
    normalized_quote: Optional[str] = None
    quote_fingerprint: Optional[str] = None
    occurrence_key: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values for cleaner output."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    def to_neo4j_dict(self) -> Dict[str, Any]:
        """Return the full enriched payload consumed by the Neo4j populator."""
        return self.to_dict()


@dataclass
class PageMetadata:
    """Classification and defaults inferred from a Wikiquote page."""
    title: str
    page_type: str
    default_author: str
    default_source: Optional[str]
    inferred_author: Optional[str] = None
    inferred_work: Optional[str] = None


class MWParserQuoteExtractor:
    """
    Advanced quote extractor for Wikiquote XML dumps.
    
    Features:
    - Template-based quote extraction ({{quote}}, {{cquote}}, etc.)
    - Multiple attribution parsing strategies
    - Configurable validation rules
    - Built-in deduplication
    - Foreign language quote handling
    - Section-aware extraction (skips disputed/misattributed)
    """
    
    def __init__(self):
        self.processed_pages = 0
        self.total_quotes = 0
        self.duplicate_stats = {
            'total_found': 0,
            'duplicates_removed': 0,
            'unique_kept': 0
        }
        
        # Patterns for identifying quotes in different contexts
        self.quote_indicators = [
            'quotes', 'quotations', 'sourced', 'attributed'
        ]
        
        # Sections to EXCLUDE from quote extraction (unreliable or meta content)
        self.exclude_sections = [
            'see also', 'external links', 'references', 'sources',
            'bibliography', 'further reading', 'categories', 'navigation',
            'misattributed', 'disputed', 'quotes about', 'about ',
            'incorrectly attributed', 'dubious', 'unverified'
        ]
        
        # Quote templates to extract from
        self.quote_templates = [
            'quote', 'cquote', 'quotation', 'bquote', 'rquote',
            'quote box', 'centered pull quote', 'pull quote'
        ]

        self.page_type_patterns = {
            'calendar_day': re.compile(
                r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}$'
            ),
            'list_page': re.compile(r'^(List of |Glossary of |Index of )', re.IGNORECASE),
            'tv_locator': re.compile(r'^(Season|Series)\s+\w+|^\[\d+\.\d+\]|/Season\s+\d+', re.IGNORECASE),
            'episode_locator': re.compile(r'\[\d+\.\d+\]|^Episode\s+\d+', re.IGNORECASE),
            'literary_locator': re.compile(r'^(Act|Scene|Book|Chapter|Part)\b', re.IGNORECASE),
        }
        self.compilation_page_pattern = re.compile(
            r'\b(?:'
            r'proverbs?|aphorisms?|sayings?|maxims?|idioms?|quotations?|quotes?\s+about|'
            r'opening lines|closing lines|first lines|last lines|last words|'
            r'catchphrases?|taglines?|one-liners?|insults|toasts'
            r')\b',
            re.IGNORECASE,
        )

        self.dialogue_prefix_stopwords = {
            'translation', 'source', 'sources', 'note', 'notes', 'context',
            'quoted', 'quotation', 'chapter', 'book', 'act', 'scene', 'part',
            'episode', 'season', 'series', 'variant', 'paraphrase',
        }

        self.editorial_label_prefixes = [
            'wording in',
            'unsourced variant',
            'unsourced variants',
            'german original',
            'original german',
            'english translation',
            'translation',
            'original text',
            'originally written',
            'may add',
            'source',
            'sources',
            'note',
            'notes',
            'citation',
            'citations',
            'quoted in',
            'from ',
        ]
        
        # Attribution patterns (dash followed by name/source)
        self.attribution_patterns = [
            # — Einstein, 1921
            re.compile(r'[—–-]\s*([A-Z][^,\n]+?)(?:,\s*(\d{4}))?$'),
            # ~ Author Name
            re.compile(r'~\s*([A-Z][^\n]+)$'),
            # - From "Book Title" by Author
            re.compile(r'[—–-]\s*(?:From\s+)?["""]([^"""]+)["""]\s*(?:by\s+)?([A-Z][^\n]+)?', re.IGNORECASE),
        ]
        
        self.person_role_keywords = {
            'activist', 'actor', 'actress', 'architect', 'artist', 'astronaut',
            'author', 'biologist', 'bishop', 'businessman', 'businesswoman',
            'ceo', 'chairman', 'chemist', 'composer', 'diplomat', 'director',
            'economist', 'emperor', 'engineer', 'essayist', 'explorer',
            'filmmaker', 'founder', 'general', 'historian', 'inventor',
            'journalist', 'king', 'mathematician', 'minister', 'musician',
            'novelist', 'philosopher', 'physicist', 'playwright', 'poet',
            'politician', 'president', 'prime minister', 'producer', 'queen',
            'rapper', 'saint', 'scientist', 'senator', 'singer', 'songwriter',
            'statesman', 'teacher', 'theologian', 'writer',
        }

        self.structural_author_exact = {
            'about', 'attributed', 'cast', 'dialogue', 'episode', 'episodes',
            'miscellaneous', 'other', 'quotes', 'sourced', 'tagline',
            'taglines', 'unsourced',
        }
        self.structural_author_patterns = [
            re.compile(r'^(?:episode|episodes?)\b', re.IGNORECASE),
            re.compile(r'^season\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b', re.IGNORECASE),
            re.compile(r'^(?:series|act|scene|book|chapter|part)\b', re.IGNORECASE),
            re.compile(r'^(?:19|20)\d0s$', re.IGNORECASE),
        ]

        self.stage_direction_prefixes = (
            'cartoon ', 'closing shot', 'film ', 'opening shot', 'title card',
        )

        # Generic/trivial dialogue lines that appear hundreds of times in
        # TV/film transcripts and add no quotable value.  Checked after
        # stripping trailing punctuation (.!?) so entries should be bare text.
        self._generic_dialogue: Set[str] = {
            "What do you mean", "What are you doing", "What are you talking about",
            "What do you want", "What's going on", "What are you doing here",
            "What does that mean", "Where are you going", "What did you say",
            "How do you know", "I don't think so", "What do you think",
            "What's your name", "I beg your pardon", "I don't understand",
            "What happened", "Who are you", "Are you okay", "Are you all right",
            "I don't know", "What is it", "What was that", "Let's go",
            "Come on", "Thank you", "I'm sorry", "Excuse me", "Never mind",
            "Of course", "Go ahead", "Wait a minute", "Hold on", "Shut up",
            "Get out", "Leave me alone", "What's wrong", "Nothing happened",
            "That's right", "That's not true", "I'm fine", "I'm not sure",
            "What's that", "Let me go", "I can't believe it", "Good morning",
            "Good night", "You're right", "What is this", "I have no idea",
            "What's the matter", "I can explain", "You don't understand",
            # Additional common TV/film transcript filler lines
            "What's that supposed to mean", "What did you do", "What are you saying",
            "Are you serious", "Thank you, sir", "What did he say", "Can I help you",
            "What do you want from me", "What are you talking about", "Who did this",
            "I can't do this", "I don't care", "Forget it", "Not now",
            "I told you", "I know", "Don't do this", "Please don't",
            "What are you doing to me", "How dare you", "Who are you people",
            "Get away from me", "What's happening", "Is that so", "Really",
            "You can't be serious", "I'm telling you", "Listen to me",
            "Trust me", "Believe me", "Help me", "Save me", "Follow me",
        }

        # Keep one row per occurrence; only exact duplicate occurrences are removed.
        self.seen_occurrence_keys: Set[str] = set()
        
        # Validation settings from runtime settings
        self.min_length = settings.quote_min_length
        self.max_length = settings.quote_max_length
        self.min_words = settings.quote_min_words
        self.max_words = settings.quote_max_words
        self.max_sentences = settings.quote_max_sentences
        self.min_alpha_ratio = settings.quote_min_alpha_ratio

    def _normalize_wikilink_target(self, target: str) -> str:
        """Normalize a wikilink target to a human-readable page title."""
        cleaned = (target or "").strip()
        if not cleaned:
            return ""
        cleaned = cleaned.split("#", 1)[0].strip()
        if ":" in cleaned:
            prefix, remainder = cleaned.split(":", 1)
            if prefix.lower() in {"w", "wikipedia", "q", "wikiquote"}:
                cleaned = remainder.strip()
        return cleaned.replace("_", " ").strip()

    def _wikilink_display_text(self, link: Any) -> str:
        """Return the most useful human-readable text for a wikilink node."""
        label = self._clean_quote_text(str(getattr(link, "text", "") or ""))
        if label:
            return label
        target = self._normalize_wikilink_target(str(getattr(link, "title", "") or ""))
        return self._clean_quote_text(target)

    def _canonicalize_text(self, text: str) -> str:
        """Normalize text for deduplication and stable keys."""
        normalized = unicodedata.normalize("NFKC", text or "")
        normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
        normalized = normalized.lower()
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'^[\'"“”‘’«»\-\s]+|[\'"“”‘’«»\-\s]+$', '', normalized)
        return normalized.strip()

    def _normalize_search_text(self, text: str) -> str:
        """Normalize text for punctuation-insensitive matching and quote fingerprints."""
        return normalize_search_text(text)

    def _looks_like_decade_bucket(self, text: Optional[str]) -> bool:
        """Return whether a heading is only a decade/time bucket."""
        return bool(text and re.fullmatch(r'(?:1[0-9]{3}|20[0-2][0-9])s', text.strip()))

    def _looks_like_editorial_label(self, text: Optional[str]) -> bool:
        """Return whether text looks like an editorial/source label rather than dialogue."""
        if not text:
            return False
        normalized = self._canonicalize_text(text)
        if not normalized:
            return False
        return any(
            normalized == prefix or normalized.startswith(prefix + ':') or normalized.startswith(prefix + ' ')
            for prefix in self.editorial_label_prefixes
        )

    def _looks_like_structural_author(self, text: Optional[str]) -> bool:
        """Return whether text is a section/header label rather than a real speaker/author."""
        if not text:
            return False
        cleaned = self._canonicalize_text(text)
        if not cleaned:
            return False
        if cleaned in self.structural_author_exact:
            return True
        if self._looks_like_decade_bucket(cleaned):
            return True
        return any(pattern.match(cleaned) for pattern in self.structural_author_patterns)

    def _strip_stage_directions(self, text: Optional[str]) -> str:
        """Remove leading/trailing stage directions while preserving the spoken quote."""
        cleaned = self._clean_quote_text(text or "")
        if not cleaned:
            return ""

        previous = None
        while cleaned and cleaned != previous:
            previous = cleaned
            cleaned = re.sub(r'^\[[^\[\]]{1,250}\]\s*', '', cleaned).strip()
            cleaned = re.sub(r'^\([^\(\)]{1,250}\)\s*', '', cleaned).strip()
            cleaned = re.sub(r'\s*\[[^\[\]]{1,250}\]$', '', cleaned).strip()
            cleaned = re.sub(r'\s*\([^\(\)]{1,250}\)$', '', cleaned).strip()

        return cleaned.strip(" -–—")

    def _looks_like_stage_direction(self, text: Optional[str]) -> bool:
        """Return whether text is mostly scene description rather than a quotable utterance."""
        if not text:
            return False
        cleaned = self._clean_quote_text(text)
        if not cleaned:
            return False
        if re.fullmatch(r'\[[^\[\]]{1,500}\]', cleaned):
            return True
        if re.fullmatch(r'\([^\(\)]{1,500}\)', cleaned):
            return True
        if cleaned.startswith('['):
            return True
        lowered = cleaned.lower()
        return lowered.startswith(self.stage_direction_prefixes)

    def _canonical_author_key(self, quote_dict: Dict[str, Any]) -> str:
        """Choose the best attribution key for canonical quote deduplication."""
        candidates = [
            quote_dict.get('speaker'),
            quote_dict.get('author'),
            quote_dict.get('work'),
            quote_dict.get('source'),
            quote_dict.get('page_title'),
        ]
        for candidate in candidates:
            normalized = self._canonicalize_text(candidate or "")
            if normalized and not self._looks_like_structural_author(normalized):
                return normalized
        return "unknown"

    def _looks_like_person_page(self, intro: str, wikitext: str) -> bool:
        """Infer whether the page subject is a person."""
        intro_lower = intro.lower()
        years = re.findall(r'\b(?:1[0-9]{3}|20[0-2][0-9])\b', intro)
        media_terms = (
            r'(?:film|movie|television series|tv series|television show|sitcom|novel|play|poem|song|album|opera|'
            r'video game|book|comedy|tragedy|novella|short story|story|memoir|essay|anthology|collection)'
        )

        if re.search(rf'\bis (?:an?|the)\s+(?:[a-z-]+\s+){{0,6}}{media_terms}\b', intro_lower):
            return False
        if re.search(r'\bfictional character\b', intro_lower):
            return False

        if re.search(r'\b(?:born|died|assassinated)\b', intro_lower):
            return True
        if len(years) >= 2 and re.search(r'\b(?:was|is)\b', intro_lower) and not re.search(media_terms, intro_lower):
            return True

        role_pattern = "|".join(re.escape(role) for role in sorted(self.person_role_keywords))
        if re.search(
            rf'\b(?:was|is|served as|became)\b[^.{{}}]{{0,120}}\b(?:{role_pattern})\b',
            intro,
            re.IGNORECASE,
        ):
            return True

        # Only match categories that unambiguously describe individual people,
        # not topic categories that mention professions (e.g. "Jewish philosophers"
        # or "American writers" would falsely match a topic page).
        return bool(
            re.search(
                r'\[\[Category:[^\]]*(?:\d{4}\s+births|\d{4}\s+deaths|living people)',
                wikitext,
                re.IGNORECASE,
            )
        )

    def _looks_like_tv_page(self, title: str, intro: str, wikitext: str) -> bool:
        """Infer whether the page is primarily about a television work."""
        if re.search(r'(?:^|/|\()season\s+\w+', title, re.IGNORECASE):
            return True
        # Match "(TV series)", "(television series)", "(1981 TV series)", etc.
        if re.search(r'\([^)]*\b(?:tv|television)\s+series\b[^)]*\)', title, re.IGNORECASE):
            return True
        if re.search(
            r'\bis an?\s+(?:[a-z-]+\s+){0,4}(?:television series|tv series|television show|sitcom|soap opera|anime series|web series)\b',
            intro,
            re.IGNORECASE,
        ):
            return True
        return bool(
            re.search(r'\[\[Category:[^\]]*(?:television|anime|sitcom|soap opera|tv series)', wikitext, re.IGNORECASE)
        )

    def _looks_like_film_page(self, title: str, intro: str, wikitext: str) -> bool:
        """Infer whether the page is primarily about a film or movie."""
        # Match "(film)", "(movie)", "(2004 film)", "(1942 American film)", etc.
        if re.search(r'\([^)]*\b(?:film|movie)\b[^)]*\)', title, re.IGNORECASE):
            return True
        if re.search(r'\bis an?\s+(?:[a-z-]+\s+){0,4}(?:film|movie|motion picture)\b', intro, re.IGNORECASE):
            return True
        if re.search(r'==\s*(?:Cast|Taglines)\s*==', wikitext, re.IGNORECASE):
            return True
        return bool(re.search(r'\[\[Category:[^\]]*(?:films|film series|movies)', wikitext, re.IGNORECASE))

    def _looks_like_compilation_page(self, title: str, intro: str, wikitext: str) -> bool:
        """Return whether the page is a quote compilation/list rather than a canonical source page."""
        intro_lower = intro.lower()
        if self.compilation_page_pattern.search(title):
            return True
        if re.search(r'\b(?:this page|the following|below)\b[^.]{0,120}\b(?:collects|collect|lists|features)\b', intro_lower):
            return True
        if re.search(r'\bcollection of\b', intro_lower):
            return True
        return bool(
            re.search(
                r'\[\[Category:[^\]]*(?:proverbs|aphorisms|sayings|quotations|catchphrases|taglines|one-liners)\b',
                wikitext,
                re.IGNORECASE,
            )
        )
    
    def create_quote_hash(self, quote_dict: Dict) -> str:
        """Create a content-only hash for a quote (author-independent).

        Using only the normalised text means the same sentence attributed to
        different speakers/pages still resolves to a single canonical Quote
        node in Neo4j, with separate QuoteOccurrence rows for provenance.
        """
        quote_text = self._normalize_search_text(
            quote_dict.get('normalized_quote')
            or quote_dict.get('canonical_quote')
            or quote_dict.get('quote', '')
        )
        return hashlib.md5(quote_text.encode('utf-8')).hexdigest()
    
    def is_duplicate(self, quote_dict: Dict) -> bool:
        """Check if an extracted quote row duplicates a previously seen occurrence."""
        occurrence_key = quote_dict.get('occurrence_key')
        if not occurrence_key:
            return False

        if occurrence_key in self.seen_occurrence_keys:
            return True

        self.seen_occurrence_keys.add(occurrence_key)
        return False

    def _build_occurrence_key(self, quote: ExtractedQuote) -> str:
        """Build a stable occurrence identifier for provenance retention.

        Keyed on (fingerprint, page_title, source) only.  Finer-grained fields
        like citation, context, and source_locator are intentionally excluded:
        including them created many near-duplicate rows for the same quote
        appearing in different sub-sections of the same page (e.g. a decade
        header like "1930s" vs "1940s"), inflating the output by 3–5×.
        """
        parts = [
            quote.quote_fingerprint or "",
            quote.page_title or "",
            quote.source or "",
        ]
        return hashlib.md5("||".join(parts).encode("utf-8")).hexdigest()

    def _finalize_quote(self, quote: ExtractedQuote) -> ExtractedQuote:
        """Populate normalized fields before deduplication/export."""
        quote.quote = self._strip_stage_directions(quote.quote)
        quote.author = self._clean_quote_text(quote.author)
        if quote.source is not None:
            quote.source = self._clean_quote_text(quote.source) or None
        if quote.work is not None:
            quote.work = self._clean_quote_text(quote.work) or None
        if quote.source_locator is not None:
            quote.source_locator = self._clean_quote_text(quote.source_locator) or None
        if quote.citation is not None:
            quote.citation = self._clean_quote_text(quote.citation) or None
        if quote.context is not None:
            quote.context = self._clean_quote_text(quote.context) or None
        if quote.speaker is not None:
            quote.speaker = self._clean_quote_text(quote.speaker) or None

        # Prevent author == source == page_title (a common misattribution):
        # on person/theme pages, the page title is the author, not a source.
        if quote.page_type in {"person", "theme"} and quote.work == quote.page_title:
            quote.work = None
        if quote.page_type in {"person", "theme"} and quote.source == quote.page_title:
            quote.source = None
        # On person pages, if source equals the author it's redundant.
        if quote.page_type == "person" and quote.source and quote.author:
            if self._canonicalize_text(quote.source) == self._canonicalize_text(quote.author):
                quote.source = None
        # On literary_work pages, when author-inference failed the page title
        # was used as the default_author (e.g. author="Human, All Too Human").
        # The title is already captured in page_title/source, so clear it here
        # rather than creating a spurious Author node with the work's name.
        if quote.page_type == "literary_work" and quote.author and quote.page_title:
            if self._canonicalize_text(quote.author) == self._canonicalize_text(quote.page_title):
                quote.author = ""
        if self._looks_like_decade_bucket(quote.source):
            quote.source_locator = quote.source_locator or quote.source
            quote.source = None
        if self._looks_like_decade_bucket(quote.work):
            quote.source_locator = quote.source_locator or quote.work
            quote.work = None
        if not quote.source and quote.work:
            quote.source = quote.work
        # Clear source_locator when it just repeats the source — the sub-bullet
        # parser sometimes writes the work title into both fields simultaneously,
        # producing three identical values (source / work / source_locator).
        if quote.source_locator and quote.source:
            if self._canonicalize_text(quote.source_locator) == self._canonicalize_text(quote.source):
                quote.source_locator = None
        if quote.quote_type == "sourced" and not quote.source:
            quote.quote_type = "attributed"
        quote.canonical_quote = self._canonicalize_text(quote.quote)
        quote.normalized_quote = self._normalize_search_text(quote.quote)
        quote.quote_fingerprint = self.create_quote_hash(
            {
                "quote": quote.quote,
                "canonical_quote": quote.canonical_quote,
                "normalized_quote": quote.normalized_quote,
                "author": quote.author,
                "speaker": quote.speaker,
                "source": quote.source,
                "work": quote.work,
                "page_title": quote.page_title,
            }
        )
        quote.occurrence_key = self._build_occurrence_key(quote)
        return quote

    def _should_keep_finalized_quote(self, quote: ExtractedQuote) -> bool:
        """Apply high-precision quality gates after context and attribution are resolved."""
        if not quote.quote or not self._is_valid_quote(quote.quote):
            return False
        if self._looks_like_stage_direction(quote.quote):
            return False
        if self._looks_like_structural_author(quote.author):
            return False
        if quote.speaker and self._looks_like_structural_author(quote.speaker):
            return False
        return True
    
    def parse_wikiquote_xml(self, xml_file_path: str, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Parse Wikiquote XML file using mwparserfromhell with built-in deduplication.
        
        Args:
            xml_file_path: Path to the Wikiquote XML dump file
            limit: Optional limit on number of pages to process
            
        Returns:
            List of quote dictionaries with 'quote', 'author', 'source' keys
        """
        quotes = []
        
        logger.info(f"Starting to parse {xml_file_path} with improved mwparserfromhell parser")
        logger.info(f"Validation settings: {self.min_length}-{self.max_length} chars, "
                   f"{self.min_words}-{self.max_words} words, max {self.max_sentences} sentences")
        
        try:
            # Use iterparse for memory efficiency
            context = ET.iterparse(xml_file_path, events=('start', 'end'))
            context = iter(context)
            event, root = next(context)
            
            # Get the namespace from the root element
            namespace = ''
            if root.tag.startswith('{'):
                namespace = root.tag.split('}')[0] + '}'
                logger.info(f"Detected XML namespace: {namespace}")
            
            current_page = {}
            in_page = False
            
            for event, elem in context:
                if event == 'start':
                    if elem.tag == f'{namespace}page' or elem.tag.endswith('}page') or elem.tag == 'page':
                        in_page = True
                        current_page = {}
                elif event == 'end':
                    if (elem.tag == f'{namespace}title' or elem.tag.endswith('}title') or elem.tag == 'title') and in_page:
                        current_page['title'] = elem.text or ""
                    elif (elem.tag == f'{namespace}text' or elem.tag.endswith('}text') or elem.tag == 'text') and in_page:
                        current_page['content'] = elem.text or ""
                    elif (elem.tag == f'{namespace}page' or elem.tag.endswith('}page') or elem.tag == 'page') and in_page:
                        # Process the completed page
                        title = current_page.get('title', '')
                        content = current_page.get('content', '')
                        
                        # Skip non-quote pages and redirects
                        if self._should_process_page(title, content):
                            page_quotes = self._extract_quotes_from_page(content, title)
                            
                            # Add quotes with deduplication
                            for quote in page_quotes:
                                self.duplicate_stats['total_found'] += 1
                                finalized_quote = self._finalize_quote(quote)
                                quote_dict = finalized_quote.to_neo4j_dict()
                                
                                if not self._should_keep_finalized_quote(finalized_quote):
                                    continue

                                if not self.is_duplicate(quote_dict):
                                    quotes.append(quote_dict)
                                    self.duplicate_stats['unique_kept'] += 1
                                else:
                                    self.duplicate_stats['duplicates_removed'] += 1
                            
                            if page_quotes:
                                logger.debug(f"Extracted {len(page_quotes)} quotes from '{title}'")
                                self.total_quotes += len(page_quotes)
                        
                        self.processed_pages += 1
                        if self.processed_pages % 100 == 0:
                            logger.info(f"Processed {self.processed_pages} pages, "
                                       f"found {len(quotes)} unique quotes "
                                       f"({self.duplicate_stats['duplicates_removed']} duplicates removed)")
                        
                        # Check limit
                        if limit and self.processed_pages >= limit:
                            break
                        
                        in_page = False
                        current_page = {}
                    
                    # Clear the element to save memory
                    elem.clear()
                    if elem == root:
                        root.clear()
        
        except Exception as e:
            logger.error(f"Error parsing XML: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
        
        logger.info(f"Parsing complete. Processed {self.processed_pages} pages, "
                   f"extracted {len(quotes)} unique quotes")
        logger.info(f"Deduplication: {self.duplicate_stats['total_found']} total -> "
                   f"{self.duplicate_stats['unique_kept']} unique "
                   f"({self.duplicate_stats['duplicates_removed']} duplicates removed)")
        return quotes
    
    def _should_process_page(self, title: str, content: str) -> bool:
        """Determine if a page should be processed for quotes."""
        if not title or not content:
            return False
        
        # Skip pages with colons (namespace pages)
        if ':' in title:
            return False
        
        # Skip redirects
        if content.strip().upper().startswith('#REDIRECT'):
            return False
        
        # Skip disambiguation pages
        if 'disambiguation' in title.lower():
            return False
        
        # Skip certain types of pages
        exclude_patterns = [
            r'^Category:', r'^Template:', r'^File:', r'^Image:',
            r'^Help:', r'^User:', r'^Talk:', r'^Wikiquote:',
            r'^MediaWiki:', r'^Special:'
        ]
        
        for pattern in exclude_patterns:
            if re.match(pattern, title, re.IGNORECASE):
                return False

        metadata = self._classify_page(title, content)
        return metadata.page_type not in {"calendar_day", "list_page", "maintenance"}

    def _extract_intro_plaintext(self, wikitext: str) -> str:
        """Return a cleaned version of the lead section for light classification."""
        lead = wikitext.split("==", 1)[0]
        filtered_lines = []
        for line in lead.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("[[File:", "[[Image:", "{{", "__")):
                continue
            filtered_lines.append(line)
        lead = "\n".join(filtered_lines)
        try:
            intro = self._clean_quote_text(mwparserfromhell.parse(lead).strip_code())
        except Exception:
            intro = self._clean_quote_text(lead)
        intro = re.sub(r'^[^.!?]{0,200}\bredirects here\.\s*', '', intro, flags=re.IGNORECASE)
        intro = re.sub(r'^\s*see also\b[^.!?]*\.?\s*', '', intro, flags=re.IGNORECASE)
        return intro.strip()

    def _infer_author_from_intro(self, intro: str, lead_wikitext: str) -> Optional[str]:
        """Infer a work author from the lead section when the page is about a work."""
        linked_patterns = [
            r'by\s+(?:[0-9a-z][0-9a-z .,&-]{0,80}\s+)?\[\[(?:[^|\]]+\|)?([^\]]+)\]\]',
            r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]\'s\b',
        ]
        for pattern in linked_patterns:
            linked_author = re.search(pattern, lead_wikitext, re.IGNORECASE)
            if linked_author:
                candidate = self._clean_quote_text(linked_author.group(1))
                if self._looks_like_person_name(candidate):
                    return candidate

        plain_author = re.search(
            r'\bby\s+(?:[0-9a-z][0-9a-z .,&-]{0,80}\s+)?([A-Z][A-Za-zÀ-ÖØ-öø-ÿ.\'’-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ.\'’-]+){0,5})\b',
            intro,
        )
        if plain_author:
            candidate = self._clean_quote_text(plain_author.group(1).strip(" ,.;:"))
            if self._looks_like_person_name(candidate):
                return candidate

        possessive_author = re.search(
            r'\b([A-Z][A-Za-zÀ-ÖØ-öø-ÿ.\'’-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ.\'’-]+){0,5})\'s\s+(?:[A-Z][^.!?]{0,120}\b)?(?:novel|book|play|poem|story|volume|collection|anthology|treatise|essay|dialogue|tragedy|comedy)\b',
            intro,
        )
        if possessive_author:
            candidate = self._clean_quote_text(possessive_author.group(1).strip(" ,.;:"))
            if self._looks_like_person_name(candidate):
                return candidate

        return None

    def _looks_like_disambiguation_page(self, intro: str, wikitext: str) -> bool:
        """Return whether a page is a disambiguation page rather than a quote corpus page."""
        intro_lower = intro.lower()
        wikitext_lower = wikitext.lower()
        return (
            "{{disambig" in wikitext_lower
            or re.search(r'\b(?:may|can) refer to\b', intro_lower) is not None
            or re.search(r'\bdisambiguation\b', intro_lower) is not None
        )

    def _looks_like_literary_work_page(self, intro: str, wikitext: str) -> bool:
        """Infer whether the page is primarily about a written work."""
        intro_lower = intro.lower()
        work_terms = (
            r'novel|book|play|poem|comedy|tragedy|novella|short story|story|memoir|essay|'
            r'dystopian novel|satirical novella|collection|anthology|dialogue|treatise|epic'
        )
        if re.search(rf'\bis an?\s+(?:[a-z-]+\s+){{0,6}}(?:{work_terms})\b', intro_lower):
            # Guard: historical events / periods / movements / places / religions
            # should not be classified as literary works even if they mention
            # an essay or memoir in their description.
            non_work_terms = (
                r'revolution|war|movement|period|era|empire|kingdom|republic|country|nation|'
                r'city|region|religion|philosophy|ideology|language|culture|civilization|dynasty'
            )
            if re.search(rf'\b(?:{non_work_terms})\b', intro_lower):
                return False
            return True
        if re.search(rf'\bis the\s+(?:[a-z-]+\s+){{0,6}}(?:{work_terms})\b', intro_lower):
            return True
        return bool(
            re.search(r'\[\[Category:[^\]]*(?:novels|plays|poems|books|literature|short stories|works)\b', wikitext, re.IGNORECASE)
        )

    def _classify_page(self, page_title: str, wikitext: str) -> PageMetadata:
        """Infer the page type and default attribution/source behavior."""
        lead_wikitext = wikitext.split("==", 1)[0]
        intro = self._extract_intro_plaintext(wikitext)
        title = self._clean_quote_text(page_title)
        inferred_author = self._infer_author_from_intro(intro, lead_wikitext)

        is_person_page = self._looks_like_person_page(intro, wikitext)

        if self.page_type_patterns['calendar_day'].match(title):
            return PageMetadata(title=title, page_type="calendar_day", default_author=title, default_source=title)

        if self.page_type_patterns['list_page'].match(title):
            return PageMetadata(title=title, page_type="list_page", default_author=title, default_source=title)

        if re.search(r'\b(village pump|cleanup|requested|sandbox|archive)\b', title, re.IGNORECASE):
            return PageMetadata(title=title, page_type="maintenance", default_author=title, default_source=title)

        if self._looks_like_disambiguation_page(intro, wikitext):
            return PageMetadata(title=title, page_type="list_page", default_author=title, default_source=title)

        # Title-based film/TV signals are unambiguous and must be checked
        # BEFORE the person heuristic.  Film pages whose intros mention actor
        # roles or two years (release + another date) can fire _looks_like_person_page
        # even though the title clearly identifies them as films/TV shows.
        if re.search(r'\([^)]*\b(?:film|movie)\b[^)]*\)', title, re.IGNORECASE):
            return PageMetadata(
                title=title,
                page_type="film",
                default_author=title,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )
        if re.search(r'(?:^|/|\()season\s+\w+', title, re.IGNORECASE) or \
           re.search(r'\([^)]*\b(?:tv|television)\s+series\b[^)]*\)', title, re.IGNORECASE):
            return PageMetadata(
                title=title,
                page_type="tv_show",
                default_author=title,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )

        if self._looks_like_compilation_page(title, intro, wikitext):
            return PageMetadata(title=title, page_type="list_page", default_author=title, default_source=title)

        # Person check MUST precede literary_work: person pages about prolific
        # authors (Bertrand Russell, Winston Churchill) often mention their
        # works in the intro and would be mis-detected as literary_work pages.
        if is_person_page:
            return PageMetadata(title=title, page_type="person", default_author=title, default_source=None)

        # TV/film checks MUST precede literary_work: many film intros say
        # "based on the 1973 novel" or "is a romantic drama" which triggers
        # the literary_work heuristic before the film heuristic is reached,
        # causing films to be extracted at the 150-quote person cap instead
        # of the correct 25-quote film cap.
        if self._looks_like_tv_page(title, intro, wikitext):
            return PageMetadata(
                title=title,
                page_type="tv_show",
                default_author=title,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )

        if self._looks_like_film_page(title, intro, wikitext):
            return PageMetadata(
                title=title,
                page_type="film",
                default_author=title,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )

        if self._looks_like_literary_work_page(intro, wikitext):
            return PageMetadata(
                title=title,
                page_type="literary_work",
                default_author=inferred_author or title,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )

        # Historical/geographic/ideological topic pages (e.g. "French Revolution",
        # "World War II", "Buddhism") must NOT be reclassified as literary_work
        # even if their intro mentions a "by <person>" pattern.
        _is_topic_page = bool(re.search(
            r'\b(?:revolution|war|movement|period|era|empire|kingdom|republic|'
            r'country|nation|city|region|religion|philosophy|ideology|language|'
            r'culture|civilization|dynasty|battle|conflict|century|decade|'
            r'mythology|history|biography)\b',
            intro.lower(),
        ))

        if re.search(r'\bQuotes?\b', wikitext) and re.search(r'\*\*\s*\[\[', wikitext) and "Quotes about" not in wikitext:
            if not is_person_page and inferred_author and not _is_topic_page:
                return PageMetadata(
                    title=title,
                    page_type="literary_work",
                    default_author=inferred_author,
                    default_source=title,
                    inferred_author=inferred_author,
                    inferred_work=title,
                )

        if re.search(r'\bCategory:\s*Themes\b', wikitext, re.IGNORECASE) or re.search(r'==\s*Attributed\s*==', wikitext):
            # Theme pages (Love, War, etc.) don't have a single author;
            # individual quotes carry their own attribution from sub-bullets.
            return PageMetadata(title=title, page_type="theme", default_author="", default_source=None)

        # If we have an inferred author but the author name equals the page
        # title, this is almost certainly a person page that the heuristic
        # above missed (e.g. Bertrand Russell, Winston Churchill).  Treat it
        # as a person page rather than literary_work.
        if inferred_author and not _is_topic_page:
            if self._canonicalize_text(inferred_author) == self._canonicalize_text(title):
                return PageMetadata(title=title, page_type="person", default_author=title, default_source=None)
            return PageMetadata(
                title=title,
                page_type="literary_work",
                default_author=inferred_author,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )

        return PageMetadata(title=title, page_type="theme", default_author="", default_source=None)

    def _extract_quotes_from_page(self, wikitext: str, page_title: str) -> List[ExtractedQuote]:
        """Extract quotes from a wiki page using multiple strategies."""
        quotes = []
        
        try:
            wikicode = mwparserfromhell.parse(wikitext)
            page_meta = self._classify_page(page_title, wikitext)

            if page_meta.page_type in {"calendar_day", "list_page", "maintenance"}:
                return quotes
            
            # Strategy 1: Extract from quote templates
            template_quotes = self._extract_template_quotes(wikicode, page_meta)
            quotes.extend(template_quotes)
            
            # Strategy 2: Extract from blockquotes
            blockquote_quotes = self._extract_blockquote_quotes(wikitext, page_meta)
            quotes.extend(blockquote_quotes)
            
            # Strategy 3: Extract from bullet points and sections
            section_quotes = self._extract_section_quotes(wikicode, page_meta)
            quotes.extend(section_quotes)
            
        except Exception as e:
            logger.error(f"Error parsing page '{page_title}': {e}")
        
        return quotes
    
    def _extract_template_quotes(self, wikicode, page_meta: PageMetadata) -> List[ExtractedQuote]:
        """Extract quotes from {{quote}}, {{cquote}}, etc. templates."""
        quotes = []
        
        for template in wikicode.filter_templates():
            template_name = str(template.name).strip().lower()
            
            # Check if this is a quote template
            if not any(qt in template_name for qt in self.quote_templates):
                continue
            
            try:
                # Extract quote text (usually first parameter or 'text' parameter)
                quote_text = None
                author = page_meta.default_author
                source = page_meta.default_source
                
                # Try named parameters first
                for param in template.params:
                    param_name = str(param.name).strip().lower()
                    param_value = self._clean_quote_text(str(param.value))
                    
                    if param_name in ['1', 'text', 'quote', 'content']:
                        quote_text = param_value
                    elif param_name in ['2', 'author', 'by', 'speaker']:
                        if param_value:
                            author = param_value
                    elif param_name in ['3', 'source', 'work', 'title']:
                        if param_value:
                            source = param_value
                
                # Fallback: first positional parameter
                if not quote_text and template.params:
                    quote_text = self._clean_quote_text(str(template.params[0].value))
                
                if quote_text and self._is_valid_quote(quote_text):
                    quotes.append(ExtractedQuote(
                        quote=quote_text,
                        author=author,
                        source=source,
                        work=source,
                        page_title=page_meta.title,
                        page_type=page_meta.page_type,
                        quote_type="template"
                    ))
                    
            except Exception as e:
                logger.debug(f"Error extracting template quote: {e}")
        
        return quotes
    
    def _extract_blockquote_quotes(self, wikitext: str, page_meta: PageMetadata) -> List[ExtractedQuote]:
        """Extract quotes from <blockquote> tags."""
        quotes = []
        
        # Find blockquote content
        blockquote_pattern = re.compile(
            r'<blockquote[^>]*>(.*?)</blockquote>',
            re.DOTALL | re.IGNORECASE
        )
        
        for match in blockquote_pattern.finditer(wikitext):
            content = match.group(1).strip()
            quote_text = self._clean_quote_text(content)
            
            if quote_text and self._is_valid_quote(quote_text):
                quotes.append(ExtractedQuote(
                    quote=quote_text,
                    author=page_meta.default_author,
                    source=page_meta.default_source,
                    work=page_meta.inferred_work,
                    page_title=page_meta.title,
                    page_type=page_meta.page_type,
                    quote_type="blockquote"
                ))
        
        return quotes
    
    # Maximum quotes to emit from any single page, keyed by page_type.
    # TV/film pages produce massive transcripts; hard-cap them at taglines only.
    _MAX_QUOTES_PER_PAGE: Dict[str, int] = {
        "person": 150,
        "literary_work": 150,
        "theme": 100,
        "film": 25,
        "tv_show": 25,
    }
    _MAX_QUOTES_PER_PAGE_DEFAULT = 150

    # Sections to whitelist for TV/film — only taglines are curated quotes.
    _TV_FILM_INCLUDE_SECTIONS = {"taglines", "tagline"}

    def _extract_section_quotes(self, wikicode, page_meta: PageMetadata) -> List[ExtractedQuote]:
        """Extract quotes from wiki sections (bullet points, colons, etc.)."""
        quotes = []
        max_quotes = self._MAX_QUOTES_PER_PAGE.get(
            page_meta.page_type, self._MAX_QUOTES_PER_PAGE_DEFAULT
        )
        sections = wikicode.get_sections(include_lead=True, levels=[2])

        for section in sections:
            section_str = str(section)

            # Determine section title and context
            section_title = ""
            headers = section.filter_headings()
            if headers:
                section_title = self._clean_quote_text(str(headers[0].title))

            # Skip excluded sections
            if self._is_excluded_section(section_title):
                continue

            # TV/film pages: only extract from Taglines (skip transcript sections).
            # Full dialogue transcripts are not curated quotes and inflate counts
            # by orders of magnitude compared to real Wikiquote content.
            if page_meta.page_type in {"tv_show", "film"}:
                if section_title.lower().strip() not in self._TV_FILM_INCLUDE_SECTIONS:
                    continue

            # Determine quote type based on section
            quote_type = self._determine_quote_type(section_title)

            # Extract year/period context from section
            year_context = self._extract_year_from_text(section_title)

            # Parse lines
            lines = section_str.split('\n')
            section_quotes = self._extract_quotes_from_lines(
                lines, page_meta, section_title, quote_type, year_context
            )
            quotes.extend(section_quotes)

            # Per-page cap: stop once we have enough for this page type
            if len(quotes) >= max_quotes:
                quotes = quotes[:max_quotes]
                break

        return quotes
    
    def _emit_pending(
        self,
        pending_quote: Optional["ExtractedQuote"],
        pending_has_attribution: bool,
        page_type: str,
        quotes: List["ExtractedQuote"],
    ) -> None:
        """Conditionally emit a pending quote, applying per-page-type attribution rules."""
        if pending_quote is None:
            return
        # Theme pages aggregate quotes from many different authors.  Without an
        # explicit attribution sub-bullet (** Author, ''Work'') these entries are
        # essentially anonymous and duplicate quotes that already appear on
        # higher-quality person/literary_work pages.  Drop them to avoid bloat.
        if page_type == "theme" and not pending_has_attribution:
            return
        quotes.append(pending_quote)

    def _extract_quotes_from_lines(
        self,
        lines: List[str],
        page_meta: PageMetadata,
        section_title: str,
        quote_type: str,
        year_context: Optional[str]
    ) -> List[ExtractedQuote]:
        """Extract quotes from lines within a section."""
        quotes = []
        current_author = page_meta.inferred_author or page_meta.default_author
        current_source = page_meta.default_source
        current_work = page_meta.inferred_work
        current_locator = section_title or None
        pending_quote: Optional[ExtractedQuote] = None
        # Tracks whether the pending quote has received at least one ** attribution
        # sub-bullet.  Used by theme pages to filter unattributed entries.
        pending_has_attribution: bool = False
        in_excluded_subsection = False

        for i, line in enumerate(lines):
            line = line.strip()

            # Check for section headers (any level 2-6)
            header_match = re.match(r'^(={2,6})\s*([^=]+?)\s*\1$', line)
            if header_match:
                header_text = self._clean_quote_text(header_match.group(2).strip())
                # Stop collecting quotes while inside excluded sub-sections
                # (e.g. === External links ===, === References ===)
                if self._is_excluded_section(header_text):
                    self._emit_pending(pending_quote, pending_has_attribution, page_meta.page_type, quotes)
                    pending_quote = None
                    pending_has_attribution = False
                    in_excluded_subsection = True
                    continue
                in_excluded_subsection = False
                # Check for year in sub-headers
                year = self._extract_year_from_text(header_text)
                if year:
                    year_context = year
                current_author, current_source, current_work, current_locator = self._apply_header_context(
                    page_meta,
                    header_text,
                    current_author,
                    current_source,
                    current_work,
                    current_locator,
                )
                continue

            if in_excluded_subsection:
                continue

            # Extract quotes from bullet points (*, #)
            if re.match(r'^[*#]\s+', line) and not line.startswith('**') and not line.startswith('##'):
                # Emit the previous pending quote before starting a new one
                self._emit_pending(pending_quote, pending_has_attribution, page_meta.page_type, quotes)
                pending_has_attribution = False

                quote_text = self._extract_quote_from_line(line[1:].strip())
                speaker, quote_text = self._split_speaker_prefix(quote_text)
                author = speaker or current_author

                if quote_text and not self._looks_like_structural_author(author) and self._is_valid_quote(quote_text):
                    pending_quote = ExtractedQuote(
                        quote=quote_text,
                        author=author,
                        speaker=speaker,
                        source=current_source,
                        work=current_work,
                        source_locator=current_locator,
                        page_title=page_meta.title,
                        page_type=page_meta.page_type,
                        context=section_title or current_locator,
                        quote_type=quote_type,
                        year=year_context
                    )
                else:
                    pending_quote = None
                continue

            # Extract quotes from colon-prefixed lines (:)
            # On TV/film pages every dialogue line is colon-prefixed; skipping
            # them here is redundant with the section whitelist above but acts
            # as a defence-in-depth guard in case a TV/film page slips through.
            if line.startswith(':') and not line.startswith('::'):
                if page_meta.page_type in {"tv_show", "film"}:
                    continue
                colon_text = self._extract_quote_from_line(line[1:].strip())
                speaker, colon_text = self._split_speaker_prefix(colon_text)
                author = speaker or current_author

                if colon_text and not self._looks_like_structural_author(author) and self._is_valid_quote(colon_text):
                    self._emit_pending(pending_quote, pending_has_attribution, page_meta.page_type, quotes)
                    pending_has_attribution = False
                    pending_quote = ExtractedQuote(
                        quote=colon_text,
                        author=author,
                        speaker=speaker,
                        source=current_source,
                        work=current_work,
                        source_locator=current_locator,
                        page_title=page_meta.title,
                        page_type=page_meta.page_type,
                        context=section_title or current_locator,
                        quote_type=quote_type,
                        year=year_context
                    )
                continue

            # Handle sub-bullets for attribution (**, ##, ::)
            if re.match(r'^(\*\*|##|::)\s*', line) and pending_quote:
                attribution_line = re.sub(r'^(\*\*|##|::)\s*', '', line)

                # Check for translation (foreign language handling)
                if self._looks_like_translation(attribution_line, pending_quote.quote):
                    translated = self._clean_quote_text(attribution_line)
                    if translated and self._is_valid_quote(translated):
                        pending_quote.original_text = pending_quote.quote
                        pending_quote.quote = translated
                    continue

                # Try to extract attribution info
                attribution = self._parse_attribution(attribution_line)
                if attribution:
                    author, work, locator, year = attribution
                    pending_quote.citation = attribution_line
                    pending_has_attribution = True
                    if author and not pending_quote.speaker and author != pending_quote.author:
                        pending_quote.author = author
                    if work:
                        pending_quote.work = work
                        if not pending_quote.source:
                            pending_quote.source = work
                    if locator:
                        pending_quote.source_locator = locator
                    if year:
                        pending_quote.year = year
                continue

        # Emit the last pending quote
        self._emit_pending(pending_quote, pending_has_attribution, page_meta.page_type, quotes)

        return quotes

    def _apply_header_context(
        self,
        page_meta: PageMetadata,
        header_text: str,
        current_author: str,
        current_source: Optional[str],
        current_work: Optional[str],
        current_locator: Optional[str],
    ) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        """Update extraction context based on page type and section headings."""
        if not header_text:
            return current_author, current_source, current_work, current_locator

        cleaned = self._clean_quote_text(header_text)
        if not cleaned:
            return current_author, current_source, current_work, current_locator
        if cleaned.lower() in {"quotes", "sourced", "attributed", "dialogue", "other", "about"}:
            return current_author, current_source, current_work, current_locator

        if page_meta.page_type == "person":
            if cleaned == page_meta.title:
                return current_author, current_source, current_work, current_locator
            if self._looks_like_decade_bucket(cleaned):
                return current_author, None, None, cleaned
            if self._looks_like_structural_author(cleaned):
                return current_author, current_source, current_work, current_locator
            return current_author, cleaned, cleaned, cleaned

        if page_meta.page_type == "literary_work":
            if self._looks_like_structural_author(cleaned):
                return current_author, current_source or page_meta.title, current_work or page_meta.title, current_locator
            return current_author, current_source or page_meta.title, current_work or page_meta.title, cleaned

        if page_meta.page_type in {"film", "tv_show"}:
            # A header is a character/speaker only when it both looks like a
            # dialogue speaker AND is NOT a structural label (Taglines, Cast…).
            # Without this guard "Taglines" would become current_author and all
            # tagline bullets would be dropped by _looks_like_structural_author.
            if self._looks_like_dialogue_speaker(cleaned) and not self._looks_like_structural_author(cleaned):
                return cleaned, current_source or page_meta.title, current_work or page_meta.title, current_locator
            return current_author, current_source or page_meta.title, current_work or page_meta.title, cleaned

        return current_author, current_source, current_work, cleaned

    def _looks_like_dialogue_speaker(self, text: str) -> bool:
        """Determine whether a heading or prefix is likely a speaker/character name."""
        if not text or len(text) > 50:
            return False
        if self._looks_like_editorial_label(text):
            return False
        if self.page_type_patterns['tv_locator'].search(text) or self.page_type_patterns['literary_locator'].search(text):
            return False
        if '[' in text or ']' in text:
            return False
        words = text.split()
        if len(words) > 6:
            return False
        return all(word[:1].isupper() for word in words if word and word[0].isalpha())

    def _split_speaker_prefix(self, text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Split dialogue lines into speaker and spoken quote when possible."""
        if not text or ':' not in text:
            return None, text

        speaker, remainder = text.split(':', 1)
        speaker = self._clean_quote_text(speaker)
        remainder = self._clean_quote_text(remainder)

        if not speaker or not remainder:
            return None, text
        if speaker.lower() in self.dialogue_prefix_stopwords:
            return None, text
        if self._looks_like_editorial_label(speaker):
            return None, text
        if len(speaker.split()) > 6 or len(speaker) > 50:
            return None, text
        if not self._looks_like_dialogue_speaker(speaker):
            return None, text
        if len(remainder.split()) < 2:
            return None, text
        return speaker, remainder
    
    def _extract_quote_from_line(self, text: str) -> Optional[str]:
        """Extract and clean quote text from a line."""
        if not text:
            return None
        
        try:
            parsed = mwparserfromhell.parse(text)
            clean_text = parsed.strip_code()
            clean_text = self._strip_stage_directions(clean_text)
            return clean_text if clean_text else None
        except Exception:
            return self._strip_stage_directions(text)
    
    def _clean_quote_text(self, text: str) -> str:
        """Clean quote text of wiki markup and formatting."""
        if not text:
            return ""
        
        # Remove wiki links - FIX: use group 2 if present, otherwise group 1
        text = re.sub(
            r'\[\[([^|\]]+)(?:\|([^\]]+))?\]\]',
            lambda m: m.group(2) if m.group(2) else m.group(1),
            text
        )
        
        # Remove external links [url text] -> text, [url] -> ""
        text = re.sub(r'\[https?://[^\s\]]+\s+([^\]]+)\]', r'\1', text)
        text = re.sub(r'\[https?://[^\]]+\]', '', text)
        
        # Remove bold/italic markup
        text = re.sub(r"'''([^']+)'''", r'\1', text)
        text = re.sub(r"''([^']+)''", r'\1', text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        
        # Remove templates (but try to preserve content of simple ones)
        text = re.sub(r'\{\{[^}|]+\|([^}]+)\}\}', r'\1', text)  # {{template|content}} -> content
        text = re.sub(r'\{\{[^}]+\}\}', '', text)  # Remove remaining templates
        
        # Clean up HTML entities
        html_entities = {
            '&quot;': '"', '&amp;': '&', '&lt;': '<', '&gt;': '>',
            '&nbsp;': ' ', '&ndash;': '–', '&mdash;': '—',
            '&lsquo;': "'", '&rsquo;': "'", '&ldquo;': '"', '&rdquo;': '"'
        }
        for entity, char in html_entities.items():
            text = text.replace(entity, char)
        
        # Remove reference tags
        text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
        text = re.sub(r'<ref[^>]*/>', '', text)
        
        # Remove surrounding quotes (but keep internal ones)
        text = text.strip()
        if len(text) > 2:
            if (text[0] in '"""\'\'«' and text[-1] in '"""\'\'»'):
                text = text[1:-1].strip()
        
        # Normalize whitespace
        text = ' '.join(text.split())

        return text.strip().lstrip(':; -–—').strip()
    
    def _parse_attribution(
        self, text: str
    ) -> Optional[Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]]:
        """
        Parse attribution from a line.
        
        Returns:
            Tuple of (author, work, locator, year) or None
        """
        if not text:
            return None

        raw_text = text
        cleaned_text = self._clean_quote_text(text)
        if not cleaned_text:
            return None

        author = None
        work = None
        locator = None
        year = None

        try:
            wikicode = mwparserfromhell.parse(raw_text)
            wikilinks = [
                self._wikilink_display_text(link)
                for link in wikicode.filter_wikilinks()
            ]
        except Exception:
            wikilinks = []

        # Extract year
        year_match = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', cleaned_text)
        if year_match:
            year = year_match.group(1)

        if wikilinks:
            link_iter = iter(wikilinks)
            for candidate in link_iter:
                if self._looks_like_person_name(candidate):
                    author = candidate
                    break
            if author:
                for candidate in link_iter:
                    if candidate != author and not self._looks_like_person_name(candidate):
                        work = candidate
                        break

        author_prefix_match = re.match(
            r'^\s*([A-Z][A-Za-zÀ-ÖØ-öø-ÿ.\'’-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ.\'’-]+){0,5})(?:,\s*(Jr\.?|Sr\.?|II|III|IV|V))?,\s*(.+)$',
            cleaned_text,
        )
        trailing_text = cleaned_text
        if author_prefix_match:
            candidate = author_prefix_match.group(1).strip()
            suffix = author_prefix_match.group(2)
            if suffix:
                candidate = f"{candidate}, {suffix.strip()}"
            if len(candidate.split()) >= 2 and self._looks_like_person_name(candidate):
                author = author or candidate
                trailing_text = author_prefix_match.group(3).strip()

        # Extract work title from italics (common for book titles)
        italic_match = re.search(r"''([^']+)''", raw_text)
        if italic_match and not work:
            work = self._clean_quote_text(italic_match.group(1)).rstrip(" ,.;:")

        # Extract work title from quotes
        work_match = re.search(r'["""]([^"""]+)["""]', cleaned_text)
        if work_match and not work:
            work = self._clean_quote_text(work_match.group(1)).rstrip(" ,.;:")

        if author and not work:
            locator_boundary = re.search(
                r',\s*(?=(?:Act|Scene|Book|Chapter|Part|Episode|Season|line|lines)\b)',
                trailing_text,
                re.IGNORECASE,
            )
            work_chunk = trailing_text
            if locator_boundary:
                work_chunk = trailing_text[: locator_boundary.start()].strip()
            work_chunk = re.split(r'\s*;\s*', work_chunk, maxsplit=1)[0].strip()
            work_chunk = re.sub(r'\([^)]*\d{4}[^)]*\)', '', work_chunk).strip(" ,.;:-")
            if work_chunk:
                if not re.match(
                    r'^(?:speech|address|interview|letter|lecture|sermon|remarks?|statement|quoted by|quoted in|reported in|from)\b',
                    work_chunk,
                    re.IGNORECASE,
                ):
                    work = work or work_chunk

        # Try attribution patterns
        for pattern in self.attribution_patterns:
            match = pattern.search(cleaned_text)
            if match:
                groups = match.groups()
                if groups[0]:
                    # Could be author or work title
                    potential = groups[0].strip()
                    if not author and self._looks_like_person_name(potential):
                        author = potential
                    elif not work:
                        work = potential
                if len(groups) > 1 and groups[1]:
                    if not author:
                        author = groups[1].strip()
                    elif not year:
                        year_match = re.search(r'\d{4}', groups[1])
                        if year_match:
                            year = year_match.group()
                break

        locator_match = re.search(
            r'\b((?:(?:Act|Scene|Book|Chapter|Part|Episode|Season)\s+[^,;]+|(?:line|lines)\s+[A-Za-z0-9.\-–]+)(?:,\s*(?:(?:Act|Scene|Book|Chapter|Part|Episode|Season)\s+[^,;]+|(?:line|lines)\s+[A-Za-z0-9.\-–]+))*)',
            cleaned_text,
            re.IGNORECASE,
        )
        if locator_match:
            locator = self._clean_quote_text(locator_match.group(1))

        # If we found attribution markers but no author, check if line looks like attribution
        if not author and not work:
            # Check for common attribution starters
            starters = ['from', 'in', 'letter to', 'interview', 'speech', 'address']
            text_lower = cleaned_text.lower()
            if any(text_lower.startswith(s) for s in starters):
                work = cleaned_text

        if author or work or locator or year:
            return (author, work, locator, year)
        
        return None
    
    def _looks_like_translation(self, text: str, original_quote: str) -> bool:
        """Check if text looks like a translation of the original quote.

        Only triggers on explicit translation markers.  The previous
        length-similarity heuristic incorrectly treated attribution sub-bullets
        (e.g. "''Hamlet'', Act III") as translations and silently swapped them
        into the quote field, corrupting both the quote text and attribution.
        """
        if not text or not original_quote:
            return False
        translation_markers = ['translation:', 'trans:', 'english:', 'meaning:']
        text_lower = text.lower()
        return any(marker in text_lower for marker in translation_markers)
    
    def _extract_year_from_text(self, text: str) -> Optional[str]:
        """Extract a year from text (e.g., from section headers like '1930s')."""
        if not text:
            return None
        
        # Look for decade (1930s)
        decade_match = re.search(r'\b(1[0-9]{3})s\b', text)
        if decade_match:
            return decade_match.group(1)
        
        # Look for specific year
        year_match = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', text)
        if year_match:
            return year_match.group(1)
        
        return None
    
    def _determine_quote_type(self, section_title: str) -> str:
        """Determine the quote type based on section title."""
        if not section_title:
            return "sourced"
        
        title_lower = section_title.lower()
        
        if 'attributed' in title_lower:
            return "attributed"
        if 'disputed' in title_lower or 'misattributed' in title_lower:
            return "disputed"
        if 'about' in title_lower:
            return "about"
        
        return "sourced"
    
    def _looks_like_person_name(self, text: str) -> bool:
        """Check if text looks like a person's name."""
        if not text or len(text) > 60:
            return False
        
        # Exclude common non-name words
        non_name_words = [
            'quotes', 'quotations', 'attributed', 'sourced', 'disputed',
            'misattributed', 'about', 'external', 'links', 'see', 'also',
            'references', 'bibliography', 'notes', 'interview', 'speech',
            'letter', 'from', 'season', 'series', 'episode',
            'act', 'scene', 'book', 'chapter', 'part'
        ]
        
        text_lower = text.lower()
        text_words = set(re.findall(r"[a-z]+", text_lower))
        if any(word in text_words for word in non_name_words):
            return False
        
        # Check for year patterns (likely not a name)
        if re.search(r'\b\d{4}\b', text):
            return False
        if self.page_type_patterns['tv_locator'].search(text) or self.page_type_patterns['literary_locator'].search(text):
            return False
        if '[' in text or ']' in text:
            return False
        
        # Typical name pattern: 2+ capitalized words
        words = text.split()
        if len(words) >= 1 and len(words) <= 5:
            # Most words should be capitalized
            capitalized = sum(1 for w in words if w and w[0].isupper())
            if capitalized >= len(words) * 0.6:
                return True
        
        return False
    
    def _is_excluded_section(self, section_title: str) -> bool:
        """Check if a section should be excluded from quote extraction."""
        if not section_title:
            return False
        
        section_lower = section_title.lower().strip()
        return any(excluded in section_lower for excluded in self.exclude_sections)
    
    def _is_valid_quote(self, text: str) -> bool:
        """Validate if extracted text is actually a quote."""
        text = self._strip_stage_directions(text)
        if not text:
            return False
        if self._looks_like_stage_direction(text):
            return False

        # Length checks (configurable)
        if len(text) < self.min_length or len(text) > self.max_length:
            return False

        # Word count check
        word_count = len(text.split())
        if word_count < self.min_words or word_count > self.max_words:
            return False

        # Reject generic/trivial dialogue (short questions/reactions that are
        # common in TV/film transcripts but carry no quotable value).
        if word_count <= 6 and text.rstrip('.!?') in self._generic_dialogue:
            return False
        
        # Sentence count check
        sentence_endings = text.count('.') + text.count('!') + text.count('?')
        if sentence_endings > self.max_sentences:
            return False
        
        # Exclude patterns that indicate non-quote content
        exclude_patterns = [
            r'^Category:', r'^File:', r'^Image:', r'^\[\[Category:',
            r'^#REDIRECT', r'^\{\{', r'^see also', r'^external links',
            r'^\d+\s*$',  # Just numbers
            r'^https?://',  # URLs
            r'.*\bredirects here\b.*',
            r'^not to be confused with\b',
        ]
        
        for pattern in exclude_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return False

        if self._looks_like_structural_author(text):
            return False
        
        # Minimum alphabetic character ratio
        alpha_chars = sum(1 for c in text if c.isalpha())
        if len(text) > 0 and alpha_chars / len(text) < self.min_alpha_ratio:
            return False
        
        text_lower = text.lower()
        
        # Exclude if it looks like a citation or reference
        citation_indicators = [
            r'^\s*\d+\.\s*$',  # Just a number with period
            r'^p\.\s*\d+',     # Page numbers
            r'^isbn\s',        # ISBN
            r'^retrieved\s',   # Retrieved date
        ]
        
        for indicator in citation_indicators:
            if re.match(indicator, text_lower):
                return False
        
        # NEW: Exclude attribution/source lines (not actual quotes)
        # These typically start with source indicators
        attribution_starters = [
            r'^letter\s+to\b',
            r'^from\s+(?:a\s+)?(?:letter|speech|interview|address|essay|book|cosmic)',
            r'^from\s+.+(?:\(\d{4}\)|\d+:\d+|quoted\s+in|published\s+in|available\s+in|translation\s+from)\b',
            r'^(?:as\s+)?quoted\s+(?:in|by)\b',
            r'^(?:quotes?\s+)?reported\s+in\b',
            r'^reported\s+by\b',
            r'^italics\s+as\s+in\b',
            r'^emphasis\s+(?:as\s+in|in\s+original)\b',
            r'^statement\s+(?:of|at|on|in)\b',
            r'^address\s+(?:at|to|for)\b',
            r'^poem\s+(?:by|on)\b',
            r'^(?:another\s+)?(?:variant|translation|paraphrase)',
            r'^sometimes\s+(?:paraphrased|quoted|attributed)',
            r'^\(\d{4}\)\s+as\s+quoted',
            r'^in\s+(?:a\s+)?(?:letter|speech|interview)\s+to\b',
            r'^remark\s+(?:made|at|during)\b',
            r'^source[sd]?\s*:',
            r'^note\s*:',
            r'^cf\.\s',
            r'^see\s+also\b',
            r'^vol\.\s*\d+',
            r'^chapter\s+\d+',
            r'^cited\s+(?:in|by)\b',
            r'^according\s+to\b',
            r'^attributed\s+(?:to|in)\b',
            r'^response\s+to\b',
            r'^einstein\'?s?\s+letter\b',
            r'^unsourced\s+variant\b',
            r'^\*\s*as\s+quoted',
            r'^(?:selected|proposed)\s+by\b',
            r'^quotes?\s+are\s+arranged\b',
            r'^(?:alphabetized|sorted\s+alphabetically)\s+by\b',
            r'^full\s+text\s+online$',
            r'^full\s+text\s+(?:at|on)\b',
            r'^content\s*:',
            r'^(?:written|directed)\s+and\s+(?:written|directed)\b',
            r'^\[.*title card.*\]$',
            r'^\[.*last lines.*\]$',
            r'^all\s+page\s+numbers\b',
            r'^wording\s+in\b',
            r'^unsourced\s+variants?\b',
            r'^(?:german|original\s+german|english)\s+original\s*:',
            r'^(?:german|english)\s+translation\s*:',
            r'^original(?:ly)?\s+(?:written|text)\s*:',
            r'^may\s+add\s*:',
            r'^einstein\s+and\s+religion\s*:',
            # Bibliographic/editorial note: "Title (year); commentary..."
            r'^[a-z][^.!?]{0,60}\(\d{4}\)\s*[;,:]',
            # "Title (year), p.\d+" or "Title (year), pp.\d+"
            r'^[a-z][^.!?]{0,60}\(\d{4}\)\s*,\s*pp?\.',
            # Starts with "For the title essay..." / "This essay is taken from..."
            r'^(?:for the|this)\s+(?:title\s+)?(?:essay|passage|poem|work)\b',
        ]
        
        for pattern in attribution_starters:
            if re.match(pattern, text_lower):
                return False
        
        # Exclude if it contains too many citation markers
        citation_markers = ['quoted in', 'quoted by', 'as cited', 'vol.', 'pp.', 
                           'p. ', 'isbn', 'collected papers', 'letter to', 
                           'speech at', 'address at', 'interview with',
                           'unsourced variant', 'manchester guardian']
        citation_count = sum(1 for marker in citation_markers if marker in text_lower)
        if citation_count >= 2:
            return False
        
        # Exclude if it looks like a date/publication reference
        # Pattern: starts with year in parentheses
        if re.match(r'^\(\d{4}\)', text):
            return False
        
        return True
    
    def save_quotes_to_json(self, quotes: List[Dict[str, str]], output_file: str):
        """Save extracted quotes to JSON file."""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(quotes, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(quotes)} unique quotes to {output_file}")
        except Exception as e:
            logger.error(f"Error saving quotes to JSON: {e}")
            raise


def main():
    """Main function to run the improved mwparserfromhell-based parser."""
    configure_logging(settings.log_level)
    try:
        import mwparserfromhell
    except ImportError:
        logger.error("mwparserfromhell not installed. Run: pip install mwparserfromhell")
        return
    
    # Configuration
    LIMIT = settings.parse_page_limit  # None for all pages, or set via env
    OUTPUT_FILE = str(settings.resolved_quotes_file)
    
    logger.info("=" * 60)
    logger.info("WIKIQUOTE PARSER - IMPROVED VERSION")
    logger.info("=" * 60)
    logger.info(f"Input: {settings.xml_file}")
    logger.info(f"Output: {OUTPUT_FILE}")
    logger.info(f"Page limit: {LIMIT or 'None (all pages)'}")
    
    extractor = MWParserQuoteExtractor()
    
    # Parse the XML file
    quotes = extractor.parse_wikiquote_xml(str(settings.xml_file), limit=LIMIT)
    
    # Save results
    if quotes:
        extractor.save_quotes_to_json(quotes, OUTPUT_FILE)
        
        # Print statistics
        authors = set(quote.get('author', 'Unknown') for quote in quotes)
        sources = set(quote.get('source', 'Unknown') for quote in quotes)
        
        print(f"\n{'=' * 60}")
        print("EXTRACTION RESULTS (WITH DEDUPLICATION)")
        print('=' * 60)
        print(f"Total unique quotes extracted: {len(quotes):,}")
        print(f"Unique authors: {len(authors):,}")
        print(f"Unique sources: {len(sources):,}")
        print(f"Output saved to: {OUTPUT_FILE}")
        
        # Deduplication statistics
        stats = extractor.duplicate_stats
        print(f"\n{'=' * 60}")
        print("DEDUPLICATION STATISTICS")
        print('=' * 60)
        print(f"Total quotes found: {stats['total_found']:,}")
        print(f"Unique quotes kept: {stats['unique_kept']:,}")
        print(f"Duplicates removed: {stats['duplicates_removed']:,}")
        if stats['total_found'] > 0:
            reduction_percent = (stats['duplicates_removed'] / stats['total_found']) * 100
            print(f"Duplicate reduction: {reduction_percent:.1f}%")
        
        # Show sample quotes
        print(f"\n{'=' * 60}")
        print("SAMPLE QUOTES")
        print('=' * 60)
        for i, quote in enumerate(quotes[:5], 1):
            print(f"\n{i}. \"{quote.get('quote', 'No quote text')[:100]}...\"")
            print(f"   — {quote.get('author', 'Unknown')}")
            print(f"   Source: {quote.get('source', 'Unknown')}")
        
        print(f"\n✅ The file '{OUTPUT_FILE}' is ready for database population.")
        print("   Run: python -m backend.app.cli.maintenance")
    
    else:
        print("\n❌ No quotes were extracted. Check the XML file and logs.")


if __name__ == "__main__":
    main()
