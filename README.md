# Wikiquote Voice Search

Wikiquote Voice Search is a monorepo for the "Which Quote?" NLP project. It builds a Wikiquote graph in Neo4j, supports quote autocomplete and retrieval, and exposes both:

- a modern web frontend with `Next.js`
- a Python backend with `FastAPI`

## Current Status

- Search pipeline: implemented and usable
- FastAPI backend: implemented and usable
- Next.js frontend: implemented as the new primary web interface
- Voice add-ons: implemented but optional (some features require heavy dependencies like NeMo)

## Core Capabilities

- Parse Wikiquote XML with `mwparserfromhell`
- Deduplicate and validate quote extraction
- Populate Neo4j graph (`Author`, `Quote`, `Source`)
- Full-text and multi-strategy quote search
- Author search with typo-tolerant fallback
- Chat-style quote query flow in FastAPI and Streamlit
- Optional voice input/output:
  - ASR: Whisper / NeMo / Wav2Vec2 hybrid routing
  - Speaker ID: NeMo TitaNet embeddings
  - TTS: NeMo FastPitch + HiFiGAN with gTTS fallback

## Repository Layout

```text
wikiquote-voice-search/
├── backend/
│   └── app/
│       ├── main.py
│       ├── routers/
│       ├── schemas/
│       └── state.py
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── tests/
├── requirements.txt
├── scripts/
│   ├── check_neo4j.py
│   ├── demo_autocomplete_tts.py
│   ├── demo_hybrid_asr.py
│   ├── parse_wikitext.py
│   ├── populate_neo4j.py
│   ├── create_index.py
│   └── enroll_user.py
├── services/
│   ├── asr_service.py
│   ├── asr_service_hybrid.py
│   ├── chatbot_service.py
│   ├── orchestrator.py
│   ├── speaker_identification.py
│   ├── tts_service.py
│   └── tts_service_simple.py
├── src/wikiquote_voice/
│   ├── config.py
│   ├── search/service.py
│   ├── dialogue/
│   └── storage/sqlite.py
├── docs/
│   └── AUTOCOMPLETE_TTS.md
└── data/
```

## Prerequisites

- Python 3.8+
- Neo4j 5+
- A valid `.env` file (copy from `.env.example`)

## Installation

```bash
git clone https://github.com/amirshahdadian/wikiquote-voice-search.git
cd wikiquote-voice-search
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your Neo4j credentials. For a local single-instance Neo4j Desktop
or server setup on macOS, prefer `bolt://127.0.0.1:7687` over `neo4j://127.0.0.1:7687`.

### Frontend Setup

```bash
cd frontend
npm install
cd ..
```

## Data Pipeline

### 1) Parse Wikiquote XML

```bash
python3 scripts/parse_wikitext.py
```

### 2) Populate Neo4j

```bash
python3 scripts/populate_neo4j.py
```

### 3) Create Indexes

```bash
python3 scripts/create_index.py
```

## Run the New Web App

### 1) Start the FastAPI backend

```bash
source venv/bin/activate
uvicorn backend.app.main:app --reload
```

### 2) Start the Next.js frontend

```bash
cd frontend
npm run dev
```

The frontend expects the API at `http://127.0.0.1:8000` by default. Override it with:

```bash
export NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Run Search Service in CLI Mode

```bash
PYTHONPATH=src python3 -m wikiquote_voice.search.service --interactive
```

## Voice Features (Optional)

### ASR (works with Whisper by default)

```bash
python3 scripts/demo_hybrid_asr.py
```

### Speaker Identification + NeMo TTS

Install NeMo only if you need these features (large dependency):

```bash
pip install "nemo-toolkit[asr,tts]>=2.4,<3"
```

The NeMo-backed services now target NeMo 2.x model names by default:

- `NEMO_TTS_SPEC_MODEL=tts_en_fastpitch`
- `NEMO_TTS_VOCODER_MODEL=tts_en_hifigan`
- `NEMO_SPEAKER_MODEL=titanet_large`
- `NEMO_ASR_MODEL=stt_en_conformer_ctc_small`

On Apple Silicon, `auto` now prefers `mps` for Whisper and Wav2Vec2 workloads, while
NeMo-backed services stay on CPU by default.

Enroll users:

```bash
python3 scripts/enroll_user.py
```

Run end-to-end voice orchestrator:

```bash
python3 services/orchestrator.py
```

## Testing Utilities

```bash
./venv/bin/python -m unittest discover -s tests -q
python3 -m compileall backend src services tests
python3 scripts/check_neo4j.py
```

### Frontend tests

```bash
cd frontend
npm run test
npm run typecheck
```

## Notes

- `build_semantic_index()` in search service is currently a warmup hook and does not build an actual semantic index.
- Relevance scores are strategy-dependent and not all are normalized to the same scale.
- Generated response audio is served from `data/api_audio/` through `GET /api/audio/{audio_id}`.

## License

See `LICENSE`.
