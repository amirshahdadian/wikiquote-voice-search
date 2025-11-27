import xml.etree.ElementTree as ET
import mwparserfromhell
import json
import re
import logging
import hashlib
import sys
from pathlib import Path
from typing import List, Dict, Optional, Set
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wikiquote_voice import Config

# Set up logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL), 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MWParserQuoteExtractor:
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
        
        # Patterns to exclude from quote extraction
        self.exclude_sections = [
            'see also', 'external links', 'references', 'sources',
            'bibliography', 'further reading', 'categories', 'navigation'
        ]
        
        # For deduplication
        self.seen_quote_hashes: Set[str] = set()
    
    def create_quote_hash(self, quote_dict: Dict) -> str:
        """Create a unique hash for a quote based on its content."""
        # Use quote text and author for uniqueness, ignore source variations
        quote_text = quote_dict.get('quote', '').strip().lower()
        author = quote_dict.get('author', '').strip().lower()
        
        # Remove extra whitespace and normalize
        quote_text = ' '.join(quote_text.split())
        author = ' '.join(author.split())
        
        # Create hash from normalized content
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
        """Parse Wikiquote XML file using mwparserfromhell with built-in deduplication."""
        quotes = []
        
        logger.info(f"Starting to parse {xml_file_path} with mwparserfromhell (with deduplication)")
        
        try:
            # First, let's examine the XML structure to get the correct namespace
            with open(xml_file_path, 'r', encoding='utf-8') as f:
                # Read first few lines to identify namespace
                first_lines = ''.join(f.readline() for _ in range(10))
                logger.info(f"XML header: {first_lines[:500]}")
            
            # Use iterparse for memory efficiency with dynamic namespace detection
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
                        logger.debug("Started processing new page")
                elif event == 'end':
                    if (elem.tag == f'{namespace}title' or elem.tag.endswith('}title') or elem.tag == 'title') and in_page:
                        current_page['title'] = elem.text or ""
                        logger.debug(f"Found title: {current_page['title']}")
                    elif (elem.tag == f'{namespace}text' or elem.tag.endswith('}text') or elem.tag == 'text') and in_page:
                        current_page['content'] = elem.text or ""
                        logger.debug(f"Found content: {len(current_page['content'])} characters")
                    elif (elem.tag == f'{namespace}page' or elem.tag.endswith('}page') or elem.tag == 'page') and in_page:
                        # Process the completed page
                        title = current_page.get('title', '')
                        content = current_page.get('content', '')
                        
                        logger.debug(f"Processing page: {title}")
                        
                        # Skip non-quote pages and redirects
                        if self._should_process_page(title, content):
                            logger.info(f"Processing page: {title}")
                            page_quotes = self._extract_quotes_from_page(content, title)
                            
                            # Add quotes with deduplication
                            for quote in page_quotes:
                                self.duplicate_stats['total_found'] += 1
                                
                                if not self.is_duplicate(quote):
                                    quotes.append(quote)
                                    self.duplicate_stats['unique_kept'] += 1
                                else:
                                    self.duplicate_stats['duplicates_removed'] += 1
                            
                            if page_quotes:
                                logger.info(f"Extracted {len(page_quotes)} quotes from '{title}' ({self.duplicate_stats['duplicates_removed']} duplicates removed)")
                                self.total_quotes += len(page_quotes)
                        else:
                            logger.debug(f"Skipping page: {title}")
                        
                        self.processed_pages += 1
                        if self.processed_pages % 10 == 0:  # More frequent logging for debugging
                            logger.info(f"Processed {self.processed_pages} pages, found {len(quotes)} unique quotes ({self.duplicate_stats['duplicates_removed']} duplicates removed)")
                        
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
        
        logger.info(f"Parsing complete. Processed {self.processed_pages} pages, extracted {len(quotes)} unique quotes")
        logger.info(f"Deduplication stats: {self.duplicate_stats['total_found']} total -> {self.duplicate_stats['unique_kept']} unique ({self.duplicate_stats['duplicates_removed']} duplicates removed)")
        return quotes
    
    def _should_process_page(self, title: str, content: str) -> bool:
        """Determine if a page should be processed for quotes."""
        logger.debug(f"Checking if should process: {title[:50]}...")
        
        # Skip empty pages
        if not title or not content:
            logger.debug("Skipping: empty title or content")
            return False
        
        # Skip pages with colons (namespace pages) - but be more specific
        if ':' in title:
            # Allow some namespace pages that might have quotes
            allowed_namespaces = []  # We can add specific ones if needed
            namespace = title.split(':')[0]
            if namespace not in allowed_namespaces:
                logger.debug(f"Skipping namespace page: {namespace}")
                return False
        
        # Skip redirects
        if content.strip().upper().startswith('#REDIRECT'):
            logger.debug("Skipping: redirect page")
            return False
        
        # Skip disambiguation pages
        if 'disambiguation' in title.lower():
            logger.debug("Skipping: disambiguation page")
            return False
        
        # Skip certain types of pages
        exclude_patterns = [
            r'^Category:', r'^Template:', r'^File:', r'^Image:',
            r'^Help:', r'^User:', r'^Talk:', r'^Wikiquote:',
            r'^MediaWiki:', r'^Special:'
        ]
        
        for pattern in exclude_patterns:
            if re.match(pattern, title, re.IGNORECASE):
                logger.debug(f"Skipping: matches exclude pattern {pattern}")
                return False
        
        logger.debug(f"Will process: {title}")
        return True
    
    def _extract_quotes_from_page(self, wikitext: str, page_title: str) -> List[Dict[str, str]]:
        """Extract quotes from a wiki page using mwparserfromhell."""
        quotes = []
        
        try:
            # Parse the wikitext
            wikicode = mwparserfromhell.parse(wikitext)
            
            # Get all sections
            sections = wikicode.get_sections(include_lead=True)
            
            for section in sections:
                section_quotes = self._extract_quotes_from_section(str(section), page_title)
                quotes.extend(section_quotes)
        
        except Exception as e:
            logger.error(f"Error parsing page '{page_title}': {e}")
        
        return quotes
    
    def _extract_quotes_from_section(self, section_text: str, page_title: str) -> List[Dict[str, str]]:
        """Extract quotes from a wiki section."""
        quotes = []
        lines = section_text.split('\n')
        
        current_author = page_title  # Default author is the page title
        current_section_title = ""
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Check for section headers to determine context/author
            header_match = re.match(r'^(={2,6})\s*([^=]+?)\s*\1$', line)
            if header_match:
                header_text = header_match.group(2).strip()
                current_section_title = header_text
                
                # If the header looks like a person's name, use it as author
                if self._looks_like_person_name(header_text):
                    current_author = header_text
                elif not self._is_excluded_section(header_text):
                    # Reset to page title for other sections
                    current_author = page_title
                continue
            
            # Skip if we're in an excluded section
            if self._is_excluded_section(current_section_title):
                continue
            
            # Extract quotes from bullet points
            if line.startswith('*') and not line.startswith('**'):
                quote_text = self._extract_quote_from_bullet(line)
                
                if quote_text and self._is_valid_quote(quote_text):
                    # Look for author attribution in the next few lines
                    attributed_author = self._find_attribution(lines, i, current_author)
                    
                    quotes.append({
                        'quote': quote_text,
                        'author': attributed_author,
                        'source': page_title
                    })
            
            # Handle sub-bullets for author attribution
            elif line.startswith('**') and quotes:
                # This might be attribution for the previous quote
                attribution = self._extract_attribution_from_line(line)
                if attribution and quotes:
                    # Update the last quote's author if it was generic
                    last_quote = quotes[-1]
                    if last_quote['author'] == page_title:
                        quotes[-1]['author'] = attribution
        
        return quotes
    
    def _extract_quote_from_bullet(self, line: str) -> Optional[str]:
        """Extract quote text from a bullet point line."""
        # Remove the bullet point
        text = line[1:].strip()
        
        if not text:
            return None
        
        # Parse with mwparserfromhell to handle wiki markup
        try:
            parsed = mwparserfromhell.parse(text)
            
            # Convert to plain text, removing templates and links
            clean_text = parsed.strip_code()
            
            # Additional cleaning
            clean_text = self._clean_quote_text(clean_text)
            
            return clean_text if clean_text else None
        
        except Exception:
            # Fallback to basic cleaning
            return self._clean_quote_text(text)
    
    def _clean_quote_text(self, text: str) -> str:
        """Clean quote text of markup and formatting."""
        if not text:
            return ""
        
        # Remove common wiki markup patterns
        text = re.sub(r'\[\[([^|\]]+)(?:\|([^\]]+))?\]\]', r'\2', text)  # [[link|text]] -> text
        text = re.sub(r'\[([^\]]+)\]', r'\1', text)  # [external link] -> external link
        text = re.sub(r"'''([^']+)'''", r'\1', text)  # '''bold''' -> bold
        text = re.sub(r"''([^']+)''", r'\1', text)  # ''italic'' -> italic
        text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
        text = re.sub(r'\{\{[^}]+\}\}', '', text)  # Remove templates
        
        # Clean up HTML entities
        text = text.replace('&quot;', '"')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&nbsp;', ' ')
        
        # Remove surrounding quotes if present
        text = re.sub(r'^["\'"](.+)["\'"]$', r'\1', text.strip())
        
        # Clean up whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    def _find_attribution(self, lines: List[str], current_index: int, default_author: str) -> str:
        """Find author attribution for a quote by looking at subsequent lines."""
        # Look at the next few lines for attribution
        for i in range(current_index + 1, min(current_index + 4, len(lines))):
            line = lines[i].strip()
            
            if line.startswith('**'):
                attribution = self._extract_attribution_from_line(line)
                if attribution:
                    return attribution
            elif line.startswith('*'):
                # Another quote started, stop looking
                break
        
        return default_author
    
    def _extract_attribution_from_line(self, line: str) -> Optional[str]:
        """Extract author attribution from a line."""
        # Remove bullets and common attribution patterns
        text = re.sub(r'^\*+\s*', '', line)
        text = re.sub(r'^[-~–—]\s*', '', text)
        
        # Parse with mwparserfromhell
        try:
            parsed = mwparserfromhell.parse(text)
            clean_text = parsed.strip_code().strip()
        except:
            clean_text = self._clean_quote_text(text)
        
        # Check if it looks like an attribution
        if clean_text and len(clean_text) < 100 and self._looks_like_attribution(clean_text):
            return clean_text
        
        return None
    
    def _looks_like_person_name(self, text: str) -> bool:
        """Check if text looks like a person's name."""
        if not text or len(text) > 50:
            return False
        
        # Remove common non-name words
        non_name_words = ['quotes', 'quotations', 'attributed', 'sourced', 'disputed', 
                         'misattributed', 'about', 'external', 'links', 'see', 'also']
        
        text_lower = text.lower()
        if any(word in text_lower for word in non_name_words):
            return False
        
        # Check for typical name patterns
        words = text.split()
        if len(words) >= 2 and all(word[0].isupper() for word in words if word):
            return True
        
        return False
    
    def _looks_like_attribution(self, text: str) -> bool:
        """Check if text looks like an author attribution."""
        if not text:
            return False
        
        # Skip if it contains quote-like content
        if len(text) > 100 or text.count('"') > 0:
            return False
        
        # Look for attribution indicators
        attribution_indicators = ['from', 'in', 'interview', 'speech', 'letter', 'book']
        if any(indicator in text.lower() for indicator in attribution_indicators):
            return True
        
        # Check if it looks like a person's name or source
        return self._looks_like_person_name(text) or len(text.split()) <= 5
    
    def _is_excluded_section(self, section_title: str) -> bool:
        """Check if a section should be excluded from quote extraction."""
        if not section_title:
            return False
        
        section_lower = section_title.lower()
        return any(excluded in section_lower for excluded in self.exclude_sections)
    
    def _is_valid_quote(self, text: str) -> bool:
        """Validate if extracted text is actually a quote - STRICTER validation."""
        if not text:
            return False
        
        # STRICT length checks - Only actual quotes (not paragraphs)
        if len(text) < 10 or len(text) > 250:
            return False
        
        # Word count check - quotes are concise
        word_count = len(text.split())
        if word_count < 3 or word_count > 40:
            return False
        
        # Sentence count check - Max 2 sentences for quotes
        sentence_count = text.count('.') + text.count('!') + text.count('?')
        if sentence_count > 2:
            return False
        
        # Exclude narrative text indicators
        narrative_indicators = [
            'referring to', 'talking about', 'in his', 'in her',
            'he said', 'she said', 'when asked', 'during an interview',
            'in the', 'at the', 'on the', 'with the'
        ]
        text_lower = text.lower()
        if any(indicator in text_lower for indicator in narrative_indicators):
            return False
        
        # Exclude certain patterns
        exclude_patterns = [
            r'^Category:', r'^File:', r'^Image:', r'^\[\[Category:',
            r'^#REDIRECT', r'^\{\{', r'^see also', r'^external links'
        ]
        
        for pattern in exclude_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return False
        
        # Exclude if it's mostly punctuation or numbers
        alpha_chars = sum(1 for c in text if c.isalpha())
        if alpha_chars < len(text) * 0.5:
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
    """Main function to run the mwparserfromhell-based parser with deduplication."""
    # Install mwparserfromhell if not already installed
    try:
        import mwparserfromhell
    except ImportError:
        logger.error("mwparserfromhell not installed. Run: pip install mwparserfromhell")
        return
    
    # Configuration
    LIMIT = None  # Process all pages for full extraction
    OUTPUT_FILE = "extracted_quotes.json"  # Final, clean output file
    
    extractor = MWParserQuoteExtractor()
    
    # Parse the XML file
    quotes = extractor.parse_wikiquote_xml(Config.XML_FILE, limit=LIMIT)
    
    # Save results
    if quotes:
        extractor.save_quotes_to_json(quotes, OUTPUT_FILE)
        
        # Print statistics
        authors = set(quote.get('author', 'Unknown') for quote in quotes)
        sources = set(quote.get('source', 'Unknown') for quote in quotes)
        
        print(f"\n=== EXTRACTION RESULTS (WITH DEDUPLICATION) ===")
        print(f"Total unique quotes extracted: {len(quotes)}")
        print(f"Unique authors: {len(authors)}")
        print(f"Unique sources: {len(sources)}")
        print(f"Output saved to: {OUTPUT_FILE}")
        
        # Deduplication statistics
        stats = extractor.duplicate_stats
        print(f"\n=== DEDUPLICATION STATISTICS ===")
        print(f"Total quotes found: {stats['total_found']:,}")
        print(f"Unique quotes kept: {stats['unique_kept']:,}")
        print(f"Duplicates removed: {stats['duplicates_removed']:,}")
        if stats['total_found'] > 0:
            reduction_percent = (stats['duplicates_removed'] / stats['total_found']) * 100
            print(f"Duplicate reduction: {reduction_percent:.1f}%")
        
        # Show sample quotes
        print(f"\n=== SAMPLE UNIQUE QUOTES ===")
        for i, quote in enumerate(quotes[:5], 1):
            print(f"{i}. \"{quote.get('quote', 'No quote text')}\"")
            print(f"   - {quote.get('author', 'Unknown')} (from {quote.get('source', 'Unknown')})")
            print()
        
        print(f"\n✅ The file '{OUTPUT_FILE}' is ready to be used for database population.")
    
    else:
        print("No quotes were extracted. Check the XML file and parsing logic.")

if __name__ == "__main__":
    main()
