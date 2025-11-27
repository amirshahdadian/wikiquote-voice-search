# 📚 Wikiquote Voice Search# Wikiquote Voice Search



An intelligent search engine for Wikiquote citations with REST API, conversational interface, and voice capabilities powered by Neo4j graph database and modern NLP.An NLP-powered search engine that extracts quotes from Wikiquote dumps and provides fast, intelligent search through a Neo4j graph database. This project implements the foundation for voice-controlled citation search with full-text indexing and autocomplete functionality.



---## Features



## 🎯 Features- **XML Parser**: Efficiently processes large Wikiquote XML dumps using mwparserfromhell

- **Advanced Extraction**: Intelligently extracts quotes, authors, and sources from Wikitext using MediaWiki parser

### ✅ STEP 1: Autocomplete Citation System (COMPLETE)- **Graph Database**: Stores relationships between quotes, authors, and sources in Neo4j

- **Neo4j Graph Database**: 858,972 quotes from 247,566 authors- **Full-text Search**: Fast autocomplete search with relevance scoring

- **FastAPI REST API**: High-performance API with automatic documentation- **Conversational Agent**: Rule-based intent parser paired with graph search for dialogue-driven discovery

- **Full-text Search**: Optimized Neo4j indexes with relevance scoring- **Batch Processing**: Memory-efficient database population with configurable batch sizes

- **Conversational Chatbot**: Natural language interface for quote discovery- **Environment Configuration**: Secure credential management using environment variables

- **Advanced Extraction**: Intelligent quote parsing using mwparserfromhell

- **Batch Processing**: Memory-efficient database population## Prerequisites



### ⚠️ STEP 2: Voice System (PARTIAL)- Python 3.8+

- **ASR (Speech Recognition)**: ✅ OpenAI Whisper implementation ready- Neo4j Database (local or remote)

- **Speaker Identification**: ⚠️ TitaNet implementation (requires NeMo)- Wikiquote XML dump file

- **Text-to-Speech**: ⚠️ FastPitch + HiFiGAN (requires NeMo)

- **Voice Pipeline**: ✅ Complete orchestrator connecting all components## Installation



---1. **Clone the repository**

    ```bash

## 🚀 Quick Start    git clone https://github.com/amirshahdadian/wikiquote-voice-search.git

    cd wikiquote-voice-search

### Prerequisites    ```

- Python 3.8+

- Neo4j Database (Desktop 2 or Server)2. **Install dependencies**

- Virtual environment recommended    ```bash

    pip install -r requirements.txt

### 1. Installation    ```



```bash3. **Set up environment variables**

# Clone the repository    ```bash

git clone https://github.com/amirshahdadian/wikiquote-voice-search.git    cp .env.example .env

cd wikiquote-voice-search    # Edit .env with your Neo4j credentials

    ```

# Create virtual environment

python3 -m venv venv4. **Download Wikiquote dump** (optional - for fresh data)

source venv/bin/activate  # On macOS/Linux    ```bash

# venv\Scripts\activate  # On Windows    # Download from https://dumps.wikimedia.org/enwikiquote/

    # Place the XML file in the project root

# Install dependencies    ```

pip install -r requirements.txt

```## Configuration



### 2. ConfigurationEdit your `.env` file with your settings:



```bash```env

# Copy environment templateNEO4J_URI=neo4j://127.0.0.1:7687

cp .env.example .envNEO4J_USERNAME=neo4j

NEO4J_PASSWORD=your_password

# Edit .env with your settingsQUOTES_FILE=extracted_quotes.json

```BATCH_SIZE=1000

SEARCH_LIMIT=5

**Required `.env` variables:**LOG_LEVEL=INFO

```envXML_FILE=enwikiquote-20250601-pages-articles.xml

NEO4J_URI=bolt://localhost:7687```

NEO4J_USERNAME=neo4j

NEO4J_PASSWORD=your_password## Usage

API_HOST=0.0.0.0

API_PORT=8000### Step 1: Extract Quotes from XML (Optional)

LOG_LEVEL=INFO

```If you have a fresh Wikiquote XML dump:



### 3. Database Setup```bash

python scripts/parse_wikitext.py

```bash```

# Start Neo4j Desktop 2 application

# Or use provided script:This will create `quotes_mwparser.json` with structured quote data using the improved mwparserfromhell parser.

./start_neo4j.sh

### Step 2: Populate Neo4j Database

# Populate database (if not already done)

python3 scripts/populate_neo4j.py```bash

python scripts/populate_neo4j.py

# Create full-text search index```

python3 scripts/create_index.py

```### Step 3: Create Full-text Index



### 4. Start the APIRun this command in Neo4j Browser:



```bash```cypher

source venv/bin/activateCREATE FULLTEXT INDEX quote_fulltext_index IF NOT EXISTS FOR (q:Quote) ON EACH [q.text]

python3 services/autocomplete_api.py```

```

### Step 4: Search Quotes

**Access points:**

- **API Documentation**: http://localhost:8000/docs```bash

- **Alternative Docs**: http://localhost:8000/redocpython -m wikiquote_voice.search.service

- **Health Check**: http://localhost:8000/health```



---### Step 5: Record Audio Queries



## 🌐 API UsageLaunch the Streamlit interface to capture microphone input and persist it for future processing:



### Search Quotes```bash

streamlit run app.py

```bash```

# Basic search (default: 5 results)

curl "http://localhost:8000/search?q=courage"The application stores each recording as a timestamped `.wav` file inside `data/recordings/`. On startup it also ensures a SQLite database (`data/wikiquote_voice.db`) exists with tables for `users`, `embeddings`, `preferences`, `favorites`, and `history`.



# Custom limit (1-50)Or use the search function programmatically:

curl "http://localhost:8000/search?q=love&limit=10"

```python

# With specific strategyfrom wikiquote_voice.search import QuoteSearchService

curl "http://localhost:8000/search?q=wisdom&limit=5&strategy=fulltext"from wikiquote_voice import Config



# Pretty formatted outputsearch_service = QuoteSearchService(

curl -s "http://localhost:8000/search?q=success&limit=5" | python3 -m json.tool     Config.NEO4J_URI, 

```     Config.NEO4J_USERNAME, 

     Config.NEO4J_PASSWORD

### Search by Author)



```bashsearch_service.connect()

curl "http://localhost:8000/search/author?author=Einstein&limit=10"results = search_service.autocomplete("wisdom", limit=5)

curl "http://localhost:8000/search/author?author=Shakespeare&limit=5"search_service.close()

curl "http://localhost:8000/search/author?author=Gandhi&limit=15"```

```

## Project Structure

### Autocomplete

```

```bashwikiquote-voice-search/

# Get suggestions as you type├── app.py                  # Streamlit entry point

curl "http://localhost:8000/autocomplete?q=cour&limit=5"├── apps/

curl "http://localhost:8000/autocomplete?q=wis&limit=8"│   ├── audio_recorder.py   # Streamlit recorder implementation

```│   └── dialogue_cli.py     # CLI for the dialogue agent

├── scripts/

### Random Quote│   ├── parse_wikitext.py   # XML parser and quote extractor

│   └── populate_neo4j.py   # Neo4j population script

```bash├── src/

curl "http://localhost:8000/random"│   └── wikiquote_voice/

```│       ├── __init__.py

│       ├── config.py       # Environment-driven configuration

### Using with Python│       ├── storage/

│       │   └── sqlite.py   # SQLite helpers for local storage

```python│       ├── dialogue/

import requests│       │   ├── __init__.py

│       │   ├── adapters.py

# Search for quotes│       │   ├── intents.py

response = requests.get(│       │   ├── manager.py

    "http://localhost:8000/search",│       │   └── nlg.py

    params={"q": "courage", "limit": 10}│       └── search/

)│           ├── __init__.py

data = response.json()│           └── service.py

├── requirements.txt

print(f"Found {data['count']} quotes:")├── README.md

for quote in data['results']:└── data/

    print(f"- \"{quote['text'][:60]}...\"")    └── recordings/         # Audio captured by the app (created at runtime)

    print(f"  — {quote['author']}")```

```

## Testing

---

Test the complete pipeline:

## 🤖 Conversational Chatbot

```bash

### Interactive Mode# Test configuration

python -c "from wikiquote_voice import Config; print('Config loaded:', Config.NEO4J_URI)"

```bash

source venv/bin/activate# Test database connection

python3 services/chatbot_service.pypython -c "

```from scripts.populate_neo4j import Neo4jPopulator

from wikiquote_voice import Config

### Available Commandspop = Neo4jPopulator(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)

- `Find quotes about [topic]` - Search by themepop.connect()

- `Show me [Author] quotes` - Search by authorprint('✅ Neo4j connection successful!')

- `another` - See more results from last searchpop.close()

- `quit` or `exit` - Close chatbot"



### Example Session# Test search

```python -c "

You: Find quotes about couragefrom wikiquote_voice.search import QuoteSearchService

Bot: Here's a quote about courage...from wikiquote_voice import Config

You: anothersearch = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)

Bot: Here's another quote...search.connect()

You: Show me Einstein quotesresults = search.autocomplete('love')

Bot: Here are quotes by Einstein...print(f'Found {len(results)} quotes')

```search.close()

"

---```



## 🎤 Voice Features (Advanced)## Extraction Improvements



### Test ASR (Speech Recognition)The current version uses `mwparserfromhell` for parsing WikiText, which provides:

- **73% more quotes extracted** compared to regex-based parsing

**Ready to use** - No additional installation needed:- **Better WikiText markup handling** 

- **More accurate author attribution**

```bash- **Cleaner quote text** with proper wiki link resolution

source venv/bin/activate

python3 -c "Previous extraction: 6,626 quotes  

from services.asr_service import ASRServiceCurrent extraction: 11,491 quotes (+4,865 additional quotes)


# Initialize ASR
asr = ASRService(model_name='base')

# Transcribe an audio file
result = asr.transcribe('path/to/audio.wav')
print(f'Transcription: {result[\"text\"]}')
"
```

### Install NeMo (For Speaker ID & TTS)

**Optional** - Only if you need speaker identification or text-to-speech:

```bash
source venv/bin/activate
pip install nemo_toolkit[asr,tts]==1.21.0
# ⏱️ Takes 15-30 minutes, downloads 2GB+
```

### Complete Voice Pipeline

```bash
source venv/bin/activate
python3 services/orchestrator.py
```

### Enroll Users (For Speaker ID)

```bash
python3 scripts/enroll_user.py
```

---

## 🎛️ Customization

### Changing API Limits

**File**: `services/autocomplete_api.py`

#### Search Endpoint (Line ~103)
```python
# Current default: 5, max: 50
limit: int = Query(5, description="Maximum results", ge=1, le=50)

# Change to: default 10, max 100
limit: int = Query(10, description="Maximum results", ge=1, le=100)
```

#### Autocomplete Endpoint (Line ~145)
```python
# Current default: 5, max: 20
limit: int = Query(5, description="Maximum results", ge=1, le=20)

# Change to: default 8, max 30
limit: int = Query(8, description="Maximum results", ge=1, le=30)
```

#### Apply Changes
```bash
# Restart API after editing
lsof -ti:8000 | xargs kill -9
python3 services/autocomplete_api.py
```

---

## 📂 Project Structure

```
wikiquote-voice-search/
├── services/                      # Main service modules
│   ├── autocomplete_api.py        # ✅ FastAPI REST API
│   ├── chatbot_service.py         # ✅ Conversational interface
│   ├── asr_service.py             # ✅ Speech recognition (Whisper)
│   ├── speaker_identification.py  # ⚠️ Speaker ID (needs NeMo)
│   ├── tts_service.py             # ⚠️ Text-to-speech (needs NeMo)
│   └── orchestrator.py            # ✅ Voice pipeline orchestrator
│
├── scripts/                       # Utility scripts
│   ├── populate_neo4j.py          # Load quotes to database
│   ├── create_index.py            # Create search indexes
│   ├── enroll_user.py             # User enrollment for Speaker ID
│   └── parse_wikitext.py          # Extract quotes from XML dumps
│
├── src/wikiquote_voice/           # Core library
│   ├── config.py                  # Configuration management
│   ├── search/
│   │   └── service.py             # Search service implementation
│   ├── dialogue/                  # Dialogue management
│   │   ├── adapters.py            # Search adapters
│   │   ├── intents.py             # Intent parsing
│   │   ├── manager.py             # Dialogue state management
│   │   └── nlg.py                 # Natural language generation
│   └── storage/
│       └── sqlite.py              # Local storage (user data, history)
│
├── docs/                          # Documentation
│   └── NEO4J_SETUP.md
├── data/                          # Data files
│   └── recordings/                # Audio recordings (runtime)
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment template
├── setup.sh                       # Setup automation script
├── test_connection.py             # Neo4j connection test
└── README.md                      # This file
```

---

## 📊 Database Statistics

- **Total Quotes**: 858,972
- **Total Authors**: 247,566
- **Total Sources**: 52,307
- **Attribution Relationships**: 858,972
- **Source Relationships**: 858,972
- **Total Graph Relationships**: 1,717,944

**Extraction Improvements**: Using mwparserfromhell parser provides:
- 73% more quotes vs regex-based parsing
- Better WikiText markup handling
- More accurate author attribution
- Cleaner quote text with proper wiki link resolution

---

## 📖 API Reference

| Endpoint | Method | Parameters | Description |
|----------|--------|------------|-------------|
| `/` | GET | - | API information and available endpoints |
| `/health` | GET | - | Health check status |
| `/search` | GET | `q` (required), `limit` (1-50), `strategy` | Search quotes by text |
| `/autocomplete` | GET | `q` (required), `limit` (1-20) | Get autocomplete suggestions |
| `/search/author` | GET | `author` (required), `limit` (1-50) | Find quotes by author |
| `/random` | GET | - | Get a random quote |

### Response Format

```json
{
  "query": "courage",
  "results": [
    {
      "text": "Quote text here...",
      "author": "Author Name",
      "source": "Source Title",
      "score": 0.95
    }
  ],
  "count": 5
}
```

---

## 🧪 Testing

### Test Configuration
```bash
python3 -c "from src.wikiquote_voice.config import Config; print('✅ Config loaded:', Config.NEO4J_URI)"
```

### Test Database Connection
```bash
python3 test_connection.py
```

### Test Search Service
```bash
python3 -c "
from src.wikiquote_voice.search.service import QuoteSearchService
from src.wikiquote_voice.config import Config

service = QuoteSearchService(Config.NEO4J_URI, Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
service.connect()
results = service.search_quotes('wisdom', limit=5)
print(f'✅ Found {len(results)} quotes')
service.close()
"
```

### Test API
```bash
# Health check
curl http://localhost:8000/health

# Search test
curl "http://localhost:8000/search?q=test&limit=3"
```

---

## 🛠️ Troubleshooting

### API Not Responding

```bash
# Check if API is running
curl http://localhost:8000/health

# Kill existing process
lsof -ti:8000 | xargs kill -9

# Restart API
source venv/bin/activate
python3 services/autocomplete_api.py
```

### Neo4j Connection Issues

```bash
# Test connection
python3 test_connection.py

# Verify Neo4j is running
# Open Neo4j Desktop 2 application
# Or check: http://localhost:7474
```

### Empty Search Results

1. **Check Neo4j is running**: Open Neo4j Desktop
2. **Verify data is loaded**: Should have 858K quotes
3. **Check full-text index**: Run `python3 scripts/create_index.py`
4. **Test with simple query**: Try searching for common words like "love" or "life"

### Port Already in Use

```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or use different port in .env
API_PORT=8001
```

---

## 🎓 Next Steps

### Current Status
- ✅ **STEP 1 Complete**: REST API, Database, Search, Chatbot fully operational
- ⚠️ **STEP 2 Partial**: ASR ready, Speaker ID/TTS need NeMo installation

### To Complete STEP 2

1. **Test ASR with audio files** (Ready now)
   ```bash
   python3 services/asr_service.py
   ```

2. **Install NeMo toolkit** (Optional, 15-30 min)
   ```bash
   pip install nemo_toolkit[asr,tts]==1.21.0
   ```

3. **Enroll users for Speaker ID**
   ```bash
   python3 scripts/enroll_user.py
   ```

4. **Test complete voice pipeline**
   ```bash
   python3 services/orchestrator.py
   ```

---

## 📝 License

See [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 🎉 System Status

- **API**: ✅ Running on http://localhost:8000
- **Database**: ✅ Neo4j with 858,972 quotes
- **Search**: ✅ Full-text indexing active
- **Chatbot**: ✅ Interactive conversational interface
- **Voice (ASR)**: ✅ Ready to test
- **Voice (Speaker ID/TTS)**: ⚠️ Needs NeMo installation

**Your system is production-ready for STEP 1!**

---

## 📚 Additional Resources

- [Neo4j Graph Database](https://neo4j.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenAI Whisper](https://github.com/openai/whisper)
- [NVIDIA NeMo](https://github.com/NVIDIA/NeMo)
- [Wikiquote Dumps](https://dumps.wikimedia.org/enwikiquote/)

---

**Built with ❤️ for intelligent quote discovery**
