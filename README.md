# Wikiquote Voice Search

An NLP-powered search engine that extracts quotes from Wikiquote dumps and provides fast, intelligent search through a Neo4j graph database. This project implements the foundation for voice-controlled citation search with full-text indexing and autocomplete functionality.

## Features

- **XML Parser**: Efficiently processes large Wikiquote XML dumps using iterative parsing
- **Regex-based Extraction**: Intelligently extracts quotes, authors, and sources from Wikitext markup
- **Graph Database**: Stores relationships between quotes, authors, and sources in Neo4j
- **Full-text Search**: Fast autocomplete search with relevance scoring
- **Batch Processing**: Memory-efficient database population with configurable batch sizes
- **Environment Configuration**: Secure credential management using environment variables

## Prerequisites

- Python 3.8+
- Neo4j Database (local or remote)
- Wikiquote XML dump file

## Installation

1. **Clone the repository**
    ```bash
    git clone https://github.com/amirshahdadian/wikiquote-voice-search.git
    cd wikiquote-voice-search
    ```

2. **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3. **Set up environment variables**
    ```bash
    cp .env.example .env
    # Edit .env with your Neo4j credentials
    ```

4. **Download Wikiquote dump** (optional - for fresh data)
    ```bash
    # Download from https://dumps.wikimedia.org/enwikiquote/
    # Place the XML file in the project root
    ```

## Configuration

Edit your `.env` file with your settings:

```env
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
QUOTES_FILE=extracted_quotes.json
BATCH_SIZE=1000
SEARCH_LIMIT=5
LOG_LEVEL=INFO
XML_FILE=enwikiquote-20250601-pages-articles.xml
```

## Usage

### Step 1: Extract Quotes from XML (Optional)

If you have a fresh Wikiquote XML dump:

```bash
python parse_wikitext.py
```

This will create `extracted_quotes.json` with structured quote data.

### Step 2: Populate Neo4j Database

```bash
python populate_db.py
```

### Step 3: Create Full-text Index

Run this command in Neo4j Browser:

```cypher
CREATE FULLTEXT INDEX quote_fulltext_index IF NOT EXISTS FOR (q:Quote) ON EACH [q.text]
```

### Step 4: Search Quotes

```bash
python search_service.py
```

Or use the search function programmatically:

```python
from search_service import QuoteSearchService
from config import Config

search_service = QuoteSearchService(
     Config.NEO4J_URI, 
     Config.NEO4J_USERNAME, 
     Config.NEO4J_PASSWORD
)

search_service.connect()
results = search_service.autocomplete("wisdom", limit=5)
search_service.close()
```

## Database Schema

The Neo4j graph database uses this schema:

- **Nodes**:
  - `(:Author {name: string})` - Quote authors
  - `(:Quote {text: string})` - Quote content
  - `(:Source {title: string})` - Source pages (movies, books, people)

- **Relationships**:
  - `(:Author)-[:ATTRIBUTED_TO]->(:Quote)` - Author attribution
  - `(:Quote)-[:APPEARS_IN]->(:Source)` - Source reference

## Project Structure

```
wikiquote-voice-search/
├── parse_wikitext.py      # XML parser and quote extractor
├── populate_db.py         # Neo4j database populator
├── search_service.py      # Search functionality
├── config.py             # Configuration management
├── requirements.txt      # Python dependencies
├── .env.example         # Environment template
├── extracted_quotes.json # Extracted quote data
└── README.md           # This file
```

## Search Features

- **Full-text search** with relevance scoring
- **Autocomplete** functionality with prefix matching
- **Author search** - find quotes by specific authors
- **Source search** - find quotes from specific works
- **Configurable result limits**

## Testing

Test the complete pipeline:

```bash
# Test configuration
python -c "from config import Config; print('Config loaded:', Config.NEO4J_URI)"

# Test database connection
python -c "
from populate_db import Neo4jPopulator
from config import Config
pop = Neo4jPopulator(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
pop.connect()
print('✅ Neo4j connection successful!')
pop.close()
"

# Test search
python -c "
from search_service import QuoteSearchService
from config import Config
search = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
search.connect()
results = search.autocomplete('love')
print(f'Found {len(results)} quotes')
search.close()
"
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact

Amir Shahdadian - amirshahdadian@gmail.com

Project Link: [https://github.com/amirshahdadian/wikiquote-voice-search](https://github.com/amirshahdadian/wikiquote-voice-search)

## Future Enhancements

- Voice recognition integration
- Text-to-speech for quote playback
- Web interface with React/Vue.js
- Advanced NLP features (sentiment analysis, topic modeling)
- Multi-language support
- Quote recommendation system

