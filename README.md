# Wikiquote Voice Search

An NLP-powered search engine that extracts quotes from Wikiquote dumps and provides fast, intelligent search through a Neo4j graph database. This project implements the foundation for voice-controlled citation search with full-text indexing and autocomplete functionality.

## Features

- **XML Parser**: Efficiently processes large Wikiquote XML dumps using mwparserfromhell
- **Advanced Extraction**: Intelligently extracts quotes, authors, and sources from Wikitext using MediaWiki parser
- **Graph Database**: Stores relationships between quotes, authors, and sources in Neo4j
- **Full-text Search**: Fast autocomplete search with relevance scoring
- **Conversational Agent**: Rule-based intent parser paired with graph search for dialogue-driven discovery
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
python scripts/parse_wikitext.py
```

This will create `quotes_mwparser.json` with structured quote data using the improved mwparserfromhell parser.

### Step 2: Populate Neo4j Database

```bash
python scripts/populate_neo4j.py
```

### Step 3: Create Full-text Index

Run this command in Neo4j Browser:

```cypher
CREATE FULLTEXT INDEX quote_fulltext_index IF NOT EXISTS FOR (q:Quote) ON EACH [q.text]
```

### Step 4: Search Quotes

```bash
python -m wikiquote_voice.search.service
```

### Step 5: Record Audio Queries

Launch the Streamlit interface to capture microphone input and persist it for future processing:

```bash
streamlit run app.py
```

The application stores each recording as a timestamped `.wav` file inside `data/recordings/`. On startup it also ensures a SQLite database (`data/wikiquote_voice.db`) exists with tables for `users`, `embeddings`, `preferences`, `favorites`, and `history`.

Or use the search function programmatically:

```python
from wikiquote_voice.search import QuoteSearchService
from wikiquote_voice import Config

search_service = QuoteSearchService(
     Config.NEO4J_URI, 
     Config.NEO4J_USERNAME, 
     Config.NEO4J_PASSWORD
)

search_service.connect()
results = search_service.autocomplete("wisdom", limit=5)
search_service.close()
```

## Project Structure

```
wikiquote-voice-search/
├── app.py                  # Streamlit entry point
├── apps/
│   ├── audio_recorder.py   # Streamlit recorder implementation
│   └── dialogue_cli.py     # CLI for the dialogue agent
├── scripts/
│   ├── parse_wikitext.py   # XML parser and quote extractor
│   └── populate_neo4j.py   # Neo4j population script
├── src/
│   └── wikiquote_voice/
│       ├── __init__.py
│       ├── config.py       # Environment-driven configuration
│       ├── storage/
│       │   └── sqlite.py   # SQLite helpers for local storage
│       ├── dialogue/
│       │   ├── __init__.py
│       │   ├── adapters.py
│       │   ├── intents.py
│       │   ├── manager.py
│       │   └── nlg.py
│       └── search/
│           ├── __init__.py
│           └── service.py
├── requirements.txt
├── README.md
└── data/
    └── recordings/         # Audio captured by the app (created at runtime)
```

## Testing

Test the complete pipeline:

```bash
# Test configuration
python -c "from wikiquote_voice import Config; print('Config loaded:', Config.NEO4J_URI)"

# Test database connection
python -c "
from scripts.populate_neo4j import Neo4jPopulator
from wikiquote_voice import Config
pop = Neo4jPopulator(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
pop.connect()
print('✅ Neo4j connection successful!')
pop.close()
"

# Test search
python -c "
from wikiquote_voice.search import QuoteSearchService
from wikiquote_voice import Config
search = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
search.connect()
results = search.autocomplete('love')
print(f'Found {len(results)} quotes')
search.close()
"
```

## Extraction Improvements

The current version uses `mwparserfromhell` for parsing WikiText, which provides:
- **73% more quotes extracted** compared to regex-based parsing
- **Better WikiText markup handling** 
- **More accurate author attribution**
- **Cleaner quote text** with proper wiki link resolution

Previous extraction: 6,626 quotes  
Current extraction: 11,491 quotes (+4,865 additional quotes)
