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
import sys
import unicodedata
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
from collections import defaultdict
from dataclasses import dataclass, field, asdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wikiquote_voice import Config

# Set up logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL), 
                   format='%(asctime)s - %(levelname)s - %(message)s')
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
        
        # For deduplication
        self.seen_quote_hashes: Set[str] = set()
        
        # Validation settings from Config
        self.min_length = Config.QUOTE_MIN_LENGTH
        self.max_length = Config.QUOTE_MAX_LENGTH
        self.min_words = Config.QUOTE_MIN_WORDS
        self.max_words = Config.QUOTE_MAX_WORDS
        self.max_sentences = Config.QUOTE_MAX_SENTENCES
        self.min_alpha_ratio = Config.QUOTE_MIN_ALPHA_RATIO

    def _canonicalize_text(self, text: str) -> str:
        """Normalize text for deduplication and stable keys."""
        normalized = unicodedata.normalize("NFKC", text or "")
        normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
        normalized = normalized.lower()
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'^[\'"“”‘’«»\-\s]+|[\'"“”‘’«»\-\s]+$', '', normalized)
        return normalized.strip()

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
    
    def create_quote_hash(self, quote_dict: Dict) -> str:
        """Create a unique hash for a quote based on its content."""
        quote_text = self._canonicalize_text(quote_dict.get('canonical_quote') or quote_dict.get('quote', ''))
        author = self._canonicalize_text(quote_dict.get('speaker') or quote_dict.get('author', ''))
        page_type = quote_dict.get('page_type', '').strip().lower()
        content = f"{quote_text}||{author}||{page_type}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def is_duplicate(self, quote_dict: Dict) -> bool:
        """Check if a quote is a duplicate and add to seen set if not."""
        quote_hash = self.create_quote_hash(quote_dict)
        
        if quote_hash in self.seen_quote_hashes:
            return True
        
        self.seen_quote_hashes.add(quote_hash)
        return False

    def _build_occurrence_key(self, quote: ExtractedQuote) -> str:
        """Build a stable occurrence identifier for provenance retention."""
        parts = [
            quote.quote_fingerprint or "",
            quote.page_title or "",
            quote.source or "",
            quote.source_locator or "",
            quote.citation or "",
            quote.context or "",
        ]
        return hashlib.md5("||".join(parts).encode("utf-8")).hexdigest()

    def _finalize_quote(self, quote: ExtractedQuote) -> ExtractedQuote:
        """Populate normalized fields before deduplication/export."""
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
        if quote.page_type in {"person", "theme"} and quote.source == quote.page_title:
            quote.source = None
        if self._looks_like_decade_bucket(quote.source):
            quote.source_locator = quote.source_locator or quote.source
            quote.source = None
        if self._looks_like_decade_bucket(quote.work):
            quote.source_locator = quote.source_locator or quote.work
            quote.work = None
        quote.canonical_quote = self._canonicalize_text(quote.quote)
        quote.quote_fingerprint = self.create_quote_hash(
            {
                "quote": quote.quote,
                "canonical_quote": quote.canonical_quote,
                "author": quote.author,
                "speaker": quote.speaker,
                "page_type": quote.page_type,
            }
        )
        quote.occurrence_key = self._build_occurrence_key(quote)
        return quote
    
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
        try:
            return self._clean_quote_text(mwparserfromhell.parse(lead).strip_code())
        except Exception:
            return self._clean_quote_text(lead)

    def _classify_page(self, page_title: str, wikitext: str) -> PageMetadata:
        """Infer the page type and default attribution/source behavior."""
        intro = self._extract_intro_plaintext(wikitext)
        title = self._clean_quote_text(page_title)
        inferred_author = None

        author_match = re.search(
            r'\bby\s+([A-Z][A-Za-z0-9 .\'’,-]{2,80})',
            intro,
        )
        if author_match:
            inferred_author = self._clean_quote_text(author_match.group(1))

        if self.page_type_patterns['calendar_day'].match(title):
            return PageMetadata(title=title, page_type="calendar_day", default_author=title, default_source=title)

        if self.page_type_patterns['list_page'].match(title):
            return PageMetadata(title=title, page_type="list_page", default_author=title, default_source=title)

        if re.search(r'\b(village pump|cleanup|requested|sandbox|archive)\b', title, re.IGNORECASE):
            return PageMetadata(title=title, page_type="maintenance", default_author=title, default_source=title)

        if re.search(r'==\s*Season\s+\w+', wikitext, re.IGNORECASE) or re.search(r'===\s*\'\'[^=]+\[\d+\.\d+\]', wikitext):
            return PageMetadata(
                title=title,
                page_type="tv_show",
                default_author=title,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )

        if re.search(r'==\s*Dialogue\s*==', wikitext, re.IGNORECASE) or re.search(r'\bDirected by\b', intro):
            return PageMetadata(
                title=title,
                page_type="film",
                default_author=title,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )

        if re.search(r'\bQuotes?\b', wikitext) and re.search(r'\*\*\s*\[\[', wikitext) and "Quotes about" not in wikitext:
            is_person_page = bool(
                re.search(r'\((?:born\s+)?\d{4}', intro)
                or re.search(r'\bwas an?\b', intro)
                or re.search(r'\bwas\b.*\b(author|poet|physicist|philosopher|actor|politician|scientist)\b', intro, re.IGNORECASE)
            )
            if not is_person_page and inferred_author:
                return PageMetadata(
                    title=title,
                    page_type="literary_work",
                    default_author=inferred_author,
                    default_source=title,
                    inferred_author=inferred_author,
                    inferred_work=title,
                )

        if re.search(r'\bCategory:\s*Themes\b', wikitext, re.IGNORECASE) or re.search(r'==\s*Attributed\s*==', wikitext):
            return PageMetadata(title=title, page_type="theme", default_author=title, default_source=None)

        is_person_page = bool(
            re.search(r'\((?:born\s+)?\d{4}', intro)
            or re.search(r'\bwas an?\b', intro)
            or re.search(r'\bwas\b.*\b(author|poet|physicist|philosopher|actor|politician|scientist)\b', intro, re.IGNORECASE)
        )
        if is_person_page:
            return PageMetadata(title=title, page_type="person", default_author=title, default_source=None)

        if inferred_author:
            return PageMetadata(
                title=title,
                page_type="literary_work",
                default_author=inferred_author,
                default_source=title,
                inferred_author=inferred_author,
                inferred_work=title,
            )

        return PageMetadata(title=title, page_type="theme", default_author=title, default_source=None)

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
    
    def _extract_section_quotes(self, wikicode, page_meta: PageMetadata) -> List[ExtractedQuote]:
        """Extract quotes from wiki sections (bullet points, colons, etc.)."""
        quotes = []
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
        
        return quotes
    
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
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Check for section headers
            header_match = re.match(r'^(={2,6})\s*([^=]+?)\s*\1$', line)
            if header_match:
                header_text = self._clean_quote_text(header_match.group(2).strip())
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
            
            # Extract quotes from bullet points (*, #)
            if re.match(r'^[*#]\s+', line) and not line.startswith('**') and not line.startswith('##'):
                # Save pending quote if any
                if pending_quote:
                    quotes.append(pending_quote)
                
                quote_text = self._extract_quote_from_line(line[1:].strip())
                speaker, quote_text = self._split_speaker_prefix(quote_text)
                author = speaker or current_author
                
                if quote_text and self._is_valid_quote(quote_text):
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
            if line.startswith(':') and not line.startswith('::'):
                colon_text = self._extract_quote_from_line(line[1:].strip())
                speaker, colon_text = self._split_speaker_prefix(colon_text)
                author = speaker or current_author
                
                if colon_text and self._is_valid_quote(colon_text):
                    if pending_quote:
                        quotes.append(pending_quote)
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
                    # This might be the actual translation, swap if needed
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
        
        # Don't forget the last pending quote
        if pending_quote:
            quotes.append(pending_quote)
        
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
            return current_author, cleaned, cleaned, cleaned

        if page_meta.page_type == "literary_work":
            return current_author, current_source or page_meta.title, current_work or page_meta.title, cleaned

        if page_meta.page_type in {"film", "tv_show"}:
            if self._looks_like_dialogue_speaker(cleaned):
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
            clean_text = self._clean_quote_text(clean_text)
            return clean_text if clean_text else None
        except Exception:
            return self._clean_quote_text(text)
    
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
        
        return text.strip()
    
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
        
        text = self._clean_quote_text(text)
        if not text:
            return None
        
        author = None
        work = None
        locator = None
        year = None
        
        # Extract year
        year_match = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', text)
        if year_match:
            year = year_match.group(1)
        
        # Try attribution patterns
        for pattern in self.attribution_patterns:
            match = pattern.search(text)
            if match:
                groups = match.groups()
                if groups[0]:
                    # Could be author or work title
                    potential = groups[0].strip()
                    if self._looks_like_person_name(potential):
                        author = potential
                    else:
                        work = potential
                if len(groups) > 1 and groups[1]:
                    if not author:
                        author = groups[1].strip()
                    elif not year:
                        year_match = re.search(r'\d{4}', groups[1])
                        if year_match:
                            year = year_match.group()
                break
        
        # Extract work title from quotes
        work_match = re.search(r'["""]([^"""]+)["""]', text)
        if work_match and not work:
            work = work_match.group(1)
        
        # Extract work title from italics (common for book titles)
        italic_match = re.search(r"''([^']+)''", text)
        if italic_match and not work:
            work = italic_match.group(1)

        locator_match = re.search(
            r'\b((?:Act|Scene|Book|Chapter|Part|Episode|Season)\s+[A-Za-z0-9.\-]+(?:,\s*(?:Scene|line|lines)\s+[A-Za-z0-9.\-–]+)?)',
            text,
            re.IGNORECASE,
        )
        if locator_match:
            locator = self._clean_quote_text(locator_match.group(1))
        
        # If we found attribution markers but no author, check if line looks like attribution
        if not author and not work:
            # Check for common attribution starters
            starters = ['from', 'in', 'letter to', 'interview', 'speech', 'address']
            text_lower = text.lower()
            if any(text_lower.startswith(s) for s in starters):
                work = text
        
        if author or work or locator or year:
            return (author, work, locator, year)
        
        return None
    
    def _looks_like_translation(self, text: str, original_quote: str) -> bool:
        """Check if text looks like a translation of the original quote."""
        if not text or not original_quote:
            return False
        
        # Check for translation markers
        translation_markers = ['translation:', 'trans:', 'english:', 'meaning:']
        text_lower = text.lower()
        if any(marker in text_lower for marker in translation_markers):
            return True
        
        # Check if similar length and different content (potential translation)
        text_clean = self._clean_quote_text(text)
        if len(text_clean) > 20 and abs(len(text_clean) - len(original_quote)) < len(original_quote) * 0.5:
            # Different enough to be a translation
            if text_clean[:20].lower() != original_quote[:20].lower():
                return True
        
        return False
    
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
            'letter', 'from', 'the', 'season', 'series', 'episode',
            'act', 'scene', 'book', 'chapter', 'part'
        ]
        
        text_lower = text.lower()
        if any(word in text_lower for word in non_name_words):
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
        if not text:
            return False
        
        # Length checks (configurable)
        if len(text) < self.min_length or len(text) > self.max_length:
            return False
        
        # Word count check
        word_count = len(text.split())
        if word_count < self.min_words or word_count > self.max_words:
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
        ]
        
        for pattern in exclude_patterns:
            if re.match(pattern, text, re.IGNORECASE):
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
    try:
        import mwparserfromhell
    except ImportError:
        logger.error("mwparserfromhell not installed. Run: pip install mwparserfromhell")
        return
    
    # Configuration
    LIMIT = Config.PARSE_PAGE_LIMIT  # None for all pages, or set via env
    OUTPUT_FILE = str(Config.QUOTES_FILE)
    
    logger.info("=" * 60)
    logger.info("WIKIQUOTE PARSER - IMPROVED VERSION")
    logger.info("=" * 60)
    logger.info(f"Input: {Config.XML_FILE}")
    logger.info(f"Output: {OUTPUT_FILE}")
    logger.info(f"Page limit: {LIMIT or 'None (all pages)'}")
    
    extractor = MWParserQuoteExtractor()
    
    # Parse the XML file
    quotes = extractor.parse_wikiquote_xml(str(Config.XML_FILE), limit=LIMIT)
    
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
        print(f"   Run: python3 scripts/populate_neo4j.py")
    
    else:
        print("\n❌ No quotes were extracted. Check the XML file and logs.")


if __name__ == "__main__":
    main()
