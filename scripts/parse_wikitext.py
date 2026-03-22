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
    source: str
    work: Optional[str] = None
    year: Optional[str] = None
    original_text: Optional[str] = None  # For foreign language quotes
    context: Optional[str] = None  # Section context (e.g., "1930s", "Interview")
    quote_type: str = "sourced"  # sourced, attributed, disputed, about
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values for cleaner output."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    def to_neo4j_dict(self) -> Dict[str, str]:
        """Convert to the format expected by Neo4j populator (quote, author, source)."""
        return {
            'quote': self.quote,
            'author': self.author,
            'source': self.source
        }


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
    
    def create_quote_hash(self, quote_dict: Dict) -> str:
        """Create a unique hash for a quote based on its content."""
        quote_text = quote_dict.get('quote', '').strip().lower()
        author = quote_dict.get('author', '').strip().lower()
        
        # Normalize whitespace
        quote_text = ' '.join(quote_text.split())
        author = ' '.join(author.split())
        
        content = f"{quote_text}||{author}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def is_duplicate(self, quote_dict: Dict) -> bool:
        """Check if a quote is a duplicate and add to seen set if not."""
        quote_hash = self.create_quote_hash(quote_dict)
        
        if quote_hash in self.seen_quote_hashes:
            return True
        
        self.seen_quote_hashes.add(quote_hash)
        return False
    
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
                                quote_dict = quote.to_neo4j_dict()
                                
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
        
        return True
    
    def _extract_quotes_from_page(self, wikitext: str, page_title: str) -> List[ExtractedQuote]:
        """Extract quotes from a wiki page using multiple strategies."""
        quotes = []
        
        try:
            wikicode = mwparserfromhell.parse(wikitext)
            
            # Strategy 1: Extract from quote templates
            template_quotes = self._extract_template_quotes(wikicode, page_title)
            quotes.extend(template_quotes)
            
            # Strategy 2: Extract from blockquotes
            blockquote_quotes = self._extract_blockquote_quotes(wikitext, page_title)
            quotes.extend(blockquote_quotes)
            
            # Strategy 3: Extract from bullet points and sections
            section_quotes = self._extract_section_quotes(wikicode, page_title)
            quotes.extend(section_quotes)
            
        except Exception as e:
            logger.error(f"Error parsing page '{page_title}': {e}")
        
        return quotes
    
    def _extract_template_quotes(self, wikicode, page_title: str) -> List[ExtractedQuote]:
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
                author = page_title
                source = page_title
                
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
                        quote_type="template"
                    ))
                    
            except Exception as e:
                logger.debug(f"Error extracting template quote: {e}")
        
        return quotes
    
    def _extract_blockquote_quotes(self, wikitext: str, page_title: str) -> List[ExtractedQuote]:
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
                    author=page_title,
                    source=page_title,
                    quote_type="blockquote"
                ))
        
        return quotes
    
    def _extract_section_quotes(self, wikicode, page_title: str) -> List[ExtractedQuote]:
        """Extract quotes from wiki sections (bullet points, colons, etc.)."""
        quotes = []
        sections = wikicode.get_sections(include_lead=True)
        
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
            
            # Extract author from section header if it looks like a person name
            section_author = page_title
            if self._looks_like_person_name(section_title):
                section_author = section_title
            
            # Extract year/period context from section
            year_context = self._extract_year_from_text(section_title)
            
            # Parse lines
            lines = section_str.split('\n')
            section_quotes = self._extract_quotes_from_lines(
                lines, section_author, page_title, quote_type, year_context
            )
            quotes.extend(section_quotes)
        
        return quotes
    
    def _extract_quotes_from_lines(
        self, 
        lines: List[str], 
        default_author: str, 
        page_title: str,
        quote_type: str,
        year_context: Optional[str]
    ) -> List[ExtractedQuote]:
        """Extract quotes from lines within a section."""
        quotes = []
        current_author = default_author
        pending_quote: Optional[ExtractedQuote] = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Check for section headers
            header_match = re.match(r'^(={2,6})\s*([^=]+?)\s*\1$', line)
            if header_match:
                header_text = header_match.group(2).strip()
                if self._looks_like_person_name(header_text):
                    current_author = self._clean_quote_text(header_text)
                # Check for year in sub-headers
                year = self._extract_year_from_text(header_text)
                if year:
                    year_context = year
                continue
            
            # Extract quotes from bullet points (*, #)
            if re.match(r'^[*#]\s+', line) and not line.startswith('**') and not line.startswith('##'):
                # Save pending quote if any
                if pending_quote:
                    quotes.append(pending_quote)
                
                quote_text = self._extract_quote_from_line(line[1:].strip())
                
                if quote_text and self._is_valid_quote(quote_text):
                    pending_quote = ExtractedQuote(
                        quote=quote_text,
                        author=current_author,
                        source=page_title,
                        quote_type=quote_type,
                        year=year_context
                    )
                else:
                    pending_quote = None
                continue
            
            # Extract quotes from colon-prefixed lines (:)
            if line.startswith(':') and not line.startswith('::'):
                colon_text = self._extract_quote_from_line(line[1:].strip())
                
                if colon_text and self._is_valid_quote(colon_text):
                    if pending_quote:
                        quotes.append(pending_quote)
                    pending_quote = ExtractedQuote(
                        quote=colon_text,
                        author=current_author,
                        source=page_title,
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
                    author, work, year = attribution
                    if author and author != pending_quote.author:
                        pending_quote.author = author
                    if work:
                        pending_quote.work = work
                    if year:
                        pending_quote.year = year
                continue
        
        # Don't forget the last pending quote
        if pending_quote:
            quotes.append(pending_quote)
        
        return quotes
    
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
    
    def _parse_attribution(self, text: str) -> Optional[Tuple[Optional[str], Optional[str], Optional[str]]]:
        """
        Parse attribution from a line.
        
        Returns:
            Tuple of (author, work, year) or None
        """
        if not text:
            return None
        
        text = self._clean_quote_text(text)
        if not text:
            return None
        
        author = None
        work = None
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
        
        # If we found attribution markers but no author, check if line looks like attribution
        if not author and not work:
            # Check for common attribution starters
            starters = ['from', 'in', 'letter to', 'interview', 'speech', 'address']
            text_lower = text.lower()
            if any(text_lower.startswith(s) for s in starters):
                work = text
        
        if author or work or year:
            return (author, work, year)
        
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
            'letter', 'from', 'the'
        ]
        
        text_lower = text.lower()
        if any(word in text_lower for word in non_name_words):
            return False
        
        # Check for year patterns (likely not a name)
        if re.search(r'\b\d{4}\b', text):
            return False
        
        # Typical name pattern: 2+ capitalized words
        words = text.split()
        if len(words) >= 2 and len(words) <= 5:
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
