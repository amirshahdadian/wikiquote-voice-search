# Wikiquote Voice Search

Wikiquote Voice Search is the repository for the Master's degree Natural Language Processing course project **"Which Quote?"**. The project follows the two mandatory steps assigned in the course:

- **Step 1**: build a Wikiquote graph database from the official English Wikiquote dump, create a full-text citation index, and provide quote autocomplete with source attribution.
- **Step 2**: build an interactive multi-user voice system on top of Step 1, with ASR, speaker identification, conversational querying, and personalized TTS responses.

This repository implements those requirements as a monorepo with:

- a `FastAPI` backend in Python
- a `Next.js` frontend
- a Neo4j-backed quote graph

## Course Context

The professor's project brief requires all groups to implement both steps:

1. **Autocomplete over Wikiquote** using a graph database built from the official dump.
2. **"Which Quote?" voice interaction** with:
   - automatic speech recognition
   - speaker recognition through stored voice embeddings
   - a chatbot layer over the quote graph
   - personalized text-to-speech

The professor mentions technologies such as Whisper, Wav2Vec2, and NVIDIA NeMo as examples. In this implementation, equivalent pre-trained components were selected to fit the target hardware and environment:

- ASR: `mlx-whisper`
- Speaker identification: `resemblyzer`
- TTS: `kokoro-onnx` with `gTTS` fallback

## Current Repository Shape

```text
wikiquote-voice-search/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routers/
│   │   │   └── schemas/
│   │   ├── cli/
│   │   ├── core/
│   │   ├── integrations/
│   │   │   └── audio/
│   │   ├── services/
│   │   ├── container.py
│   │   └── main.py
│   └── tests/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── tests/
├── data/
├── pyproject.toml
├── pytest.ini
├── requirements.txt
└── README.md
```

Notes:

- `backend/app/*` is the canonical Python backend.
- operational CLI logic lives under `backend/app/cli/*`
- the old `scripts/`, `services/`, and `src/` trees have been removed

## Core Capabilities

- Parse the official Wikiquote XML dump with `mwparserfromhell`
- Extract, normalize, validate, and deduplicate quotes
- Populate a Neo4j graph with `Author`, `Quote`, `QuoteOccurrence`, `Source`, and `Page`
- Build full-text indexes for quote lookup and autocomplete
- Support multi-strategy quote retrieval and author search
- Provide a FastAPI API for chat, quote search, users, voice queries, TTS preview, and audio serving
- Support multi-user voice interaction with:
  - ASR via `mlx-whisper`
  - speaker recognition via `resemblyzer`
  - personalized TTS via `kokoro-onnx`

## Requirements

- Python `3.11+`
- Node.js `20+` recommended
- Neo4j `5+`
- a valid `.env` file copied from `.env.example`

## Installation

### Python

```bash
git clone https://github.com/amirshahdadian/wikiquote-voice-search.git
cd wikiquote-voice-search
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Optional editable install:

```bash
pip install -e ".[dev]"
```

This also exposes the canonical CLI entrypoints:

```bash
which-quote-ingest
which-quote-maintenance
which-quote-users
```

### Frontend

```bash
cd frontend
npm install
cd ..
```

## Configuration

Edit `.env` with the Neo4j connection and any local overrides. Important values include:

- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- `FRONTEND_ORIGINS`

For a local Neo4j instance on macOS, `bolt://127.0.0.1:7687` is often simpler than `neo4j://127.0.0.1:7687`.

## Step 1 Workflow

### 1. Parse the Wikiquote dump

```bash
python -m backend.app.cli.ingest
```

or:

```bash
which-quote-ingest
```

### 2. Populate Neo4j

```bash
python -m backend.app.cli.maintenance
```

### 3. Create the Neo4j indexes

```bash
python -m backend.app.cli.maintenance --create-index
```

or:

```bash
which-quote-maintenance --create-index
```

## Step 2 Workflow

### 1. Start the FastAPI backend

```bash
source venv/bin/activate
uvicorn backend.app.main:app --reload
```

Interactive API docs:

```text
http://127.0.0.1:8000/docs
```

### 2. Start the Next.js frontend

```bash
cd frontend
npm run dev
```

The frontend expects the API at `http://127.0.0.1:8000` by default. Override it if needed:

```bash
export NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### 3. Enroll users for speaker recognition and personalized TTS

```bash
python -m backend.app.cli.users
```

or:

```bash
which-quote-users
```

## Testing

### Backend

```bash
python3 -m compileall backend
pytest -q
```

### Frontend

```bash
cd frontend
npm run test
npm run typecheck
```

## Academic Deliverables

According to the course instructions, the project delivery includes:

- source code
- a short written report
- a live demo
- a short presentation

This repository contains the codebase; the written report is in `REPORT.md`.

## Notes

- `build_semantic_index()` is currently a warmup hook, not a full semantic vector index.
- the primary TTS path is local (`kokoro-onnx`); the fallback path (`gTTS`) may require network access if used
- generated response audio is served from `data/api_audio/` through `GET /api/audio/{audio_id}`

## License

See `LICENSE`.
