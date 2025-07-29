import xml.etree.ElementTree as ET
import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from config import Config

# Set up logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL), 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WikiquoteParser:
    def __init__(self):
        # Regex patterns for extracting quotes and authors
        self.quote_patterns = [
            # Pattern 1: * Quote text
            r'^\*\s*([^*].+?)$',
            # Pattern 2: * "Quote text"
            r'^\*\s*["""](.+?)["""]',
            # Pattern 3: * '''Quote text'''
            r'^\*\s*\'\'\'(.+?)\'\'\'',
            # Pattern 4: * ''Quote text''
            r'^\*\s*\'\'(.+?)\'\''
        ]
        
        # Patterns for author attribution
        self.author_patterns = [
            # Pattern 1: ** Author Name
            r'^\*\*\s*(.+?)$',
            # Pattern 2: ** [[Author Name]]
            r'^\*\*\s*\[\[([^\]]+)\]\]',
            # Pattern 3: ** ~ Author Name
            r'^\*\*\s*~\s*(.+?)$',
            # Pattern 4: ** Source: Author Name
            r'^\*\*\s*Source:\s*(.+?)$'
        ]

    def clean_text(self, text: str) -> str:
        """Clean wikitext markup from extracted text."""
        if not text:
            return ""
        
        # Remove wiki markup
        text = re.sub(r'\[\[([^\]|]+)(\|[^\]]+)?\]\]', r'\1', text)  # [[link|text]] -> text or [[link]] -> link
        text = re.sub(r'\[([^\]]+)\]', r'\1', text)  # [external link] -> external link
        text = re.sub(r'\'\'\'([^\']+)\'\'\'', r'\1', text)  # '''bold''' -> bold
        text = re.sub(r'\'\'([^\']+)\'\'', r'\1', text)  # ''italic'' -> italic
        text = re.sub(r'&quot;', '"', text)  # HTML entities
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
        
        # Clean up whitespace
        text = ' '.join(text.split())
        return text.strip()

    def extract_quotes_from_text(self, content: str, source_title: str) -> List[Dict[str, str]]:
        """Extract quotes from wikitext content."""
        quotes = []
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines and section headers
            if not line or line.startswith('=') or line.startswith('#'):
                i += 1
                continue
            
            # Check if line matches quote pattern
            quote_text = None
            for pattern in self.quote_patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    quote_text = match.group(1)
                    break
            
            if quote_text:
                quote_text = self.clean_text(quote_text)
                
                # Look for author attribution in the next few lines
                author = None
                j = i + 1
                while j < min(i + 3, len(lines)) and not author:
                    next_line = lines[j].strip()
                    
                    for pattern in self.author_patterns:
                        match = re.match(pattern, next_line, re.IGNORECASE)
                        if match:
                            author = self.clean_text(match.group(1))
                            break
                    j += 1
                
                # If no specific author found, use the source title as author
                if not author and source_title:
                    author = source_title
                
                # Only add if quote is substantial and has an author
                if quote_text and len(quote_text) > 10 and author:
                    quotes.append({
                        'quote': quote_text,
                        'author': author,
                        'source': source_title
                    })
            
            i += 1
        
        return quotes

    def parse_wikiquote_xml(self, xml_file_path: str, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Parse Wikiquote XML file and extract quotes."""
        quotes = []
        processed_pages = 0
        
        logger.info(f"Starting to parse {xml_file_path}")
        
        try:
            # Use iterparse to handle large files efficiently
            context = ET.iterparse(xml_file_path, events=('start', 'end'))
            context = iter(context)
            event, root = next(context)
            
            current_page = {}
            in_page = False
            
            for event, elem in context:
                if event == 'start':
                    if elem.tag.endswith('page'):
                        in_page = True
                        current_page = {}
                elif event == 'end':
                    if elem.tag.endswith('title') and in_page:
                        current_page['title'] = elem.text or ""
                    elif elem.tag.endswith('text') and in_page:
                        current_page['content'] = elem.text or ""
                    elif elem.tag.endswith('page') and in_page:
                        # Process the completed page
                        title = current_page.get('title', '')
                        content = current_page.get('content', '')
                        
                        # Skip redirect pages and non-quote pages
                        if (content and not content.strip().startswith('#REDIRECT') 
                            and title and ':' not in title):  # Skip namespace pages
                            
                            page_quotes = self.extract_quotes_from_text(content, title)
                            quotes.extend(page_quotes)
                            
                            if page_quotes:
                                logger.info(f"Extracted {len(page_quotes)} quotes from '{title}'")
                        
                        processed_pages += 1
                        if processed_pages % 100 == 0:
                            logger.info(f"Processed {processed_pages} pages, found {len(quotes)} quotes total")
                        
                        # Check limit
                        if limit and processed_pages >= limit:
                            break
                        
                        in_page = False
                        current_page = {}
                    
                    # Clear the element to save memory
                    elem.clear()
                    root.clear()
        
        except ET.ParseError as e:
            logger.error(f"XML parsing error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        
        logger.info(f"Finished parsing. Processed {processed_pages} pages, extracted {len(quotes)} total quotes")
        return quotes

    def save_quotes_to_json(self, quotes: List[Dict[str, str]], output_file: str):
        """Save extracted quotes to JSON file."""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(quotes, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(quotes)} quotes to {output_file}")
        except Exception as e:
            logger.error(f"Error saving quotes to JSON: {e}")

def main():
    """Main function to run the parser."""
    # Configuration using config module
    LIMIT = 50  # Set to None for full processing, or a number for testing
    
    parser = WikiquoteParser()
    
    # Parse the XML file using config
    quotes = parser.parse_wikiquote_xml(Config.XML_FILE, limit=LIMIT)
    
    # Save to JSON using config
    if quotes:
        parser.save_quotes_to_json(quotes, Config.QUOTES_FILE)
        
        # Print some statistics
        authors = set(quote['author'] for quote in quotes)
        sources = set(quote['source'] for quote in quotes)
        
        print(f"\n=== EXTRACTION SUMMARY ===")
        print(f"Total quotes extracted: {len(quotes)}")
        print(f"Unique authors: {len(authors)}")
        print(f"Unique sources: {len(sources)}")
        print(f"Output saved to: {Config.QUOTES_FILE}")
        
        # Show a few examples
        print(f"\n=== SAMPLE QUOTES ===")
        for i, quote in enumerate(quotes[:3]):
            print(f"{i+1}. \"{quote['quote']}\" - {quote['author']} (from {quote['source']})")
    else:
        print("No quotes were extracted. Please check the XML file and parsing logic.")

if __name__ == "__main__":
    main()