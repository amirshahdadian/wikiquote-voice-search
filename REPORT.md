# Which Quote? - Final Project Report

**Natural Language Processing - Data Science Master's degree**

| | |
|---|---|
| **Team** | Amir Hossein Shahdadian · Mahtab Taheri · Yasaman Zahedan |
| **Project** | *Which Quote?* |
| **Dataset** | English Wikiquote dump - `enwikiquote-20251120-pages-articles.xml` |
| **Repository** | `wikiquote-voice-search` |

---

## Abstract

This report presents *Which Quote?*, a two-step Natural Language Processing project built on the English Wikiquote corpus. The first step constructs a Neo4j-based quotation graph from the official Wikiquote dump and provides indexed quote autocomplete and retrieval. The second step extends that graph into an interactive multi-user voice system with automatic speech recognition, speaker identification through stored embeddings, a conversational query layer, and personalized text-to-speech responses.

The final system is implemented as a full-stack application with a Python `FastAPI` backend and a `Next.js` frontend. It is designed to satisfy the academic requirements of the course project while remaining practical to demonstrate in a live presentation.

---

## 1. Assignment Context

The course project was defined in two mandatory stages.

### Step 1

- build a graph database containing Wikiquote
- start from the official English Wikiquote dump
- create a full-text index on citations
- implement a system that autocompletes user-entered quote fragments
- identify the source of the best-matching citation

### Step 2

**"Which Quote?"**, an interactive system that allows multiple users to interact vocally with the results of Step 1. The required modules were:

- an Automatic Speech Recognition module
- a Speaker Identification module based on stored voice embeddings
- a Chatbot module connected to the Wikiquote graph
- a Personalized Text-to-Speech module

The project instructions list technologies such as Whisper, Wav2Vec2, and NVIDIA NeMo as example solutions. Our implementation uses equivalent pre-trained components chosen to match the project constraints and the available hardware:

- **ASR**: `mlx-whisper`
- **Speaker Identification**: `resemblyzer`
- **TTS**: `kokoro-onnx` with `gTTS` fallback

This still respects the core assignment requirement: use pre-trained models to implement the specified pipeline.

---

## 2. Project Goals

The project was designed around two main goals.

### Goal 1: Build a usable quote-retrieval system from raw Wikiquote data

This required transforming a large and noisy MediaWiki XML dump into a structured graph with searchable, attributable quotations.

### Goal 2: Turn quote retrieval into an interactive voice-driven experience

This required combining speech recognition, speaker recognition, conversational query handling, and voice synthesis into a single end-to-end system that could be demonstrated by multiple users.

---

## 3. Final System Overview

The final system is organized as a monorepo with a canonical Python backend and a web frontend.

```text
┌─────────────────────────────────────────────────────────────┐
│                 Next.js Frontend (localhost:3000)          │
│   Chat UI · Advanced Search UI · User Management UI        │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
┌──────────────────────────────▼──────────────────────────────┐
│                FastAPI Backend (localhost:8000)            │
│                                                             │
│  API Routers                                                │
│   /api/quotes  /api/authors  /api/chat  /api/voice         │
│   /api/users   /api/tts      /api/audio /api/health        │
│                                                             │
│  Application Services                                       │
│   QuoteSearchService                                        │
│   ConversationService                                       │
│   UserService                                               │
│   VoiceService                                              │
│                                                             │
│  Integrations                                               │
│   Neo4j quote repository                                    │
│   SQLite user store                                         │
│   ASR (mlx-whisper)                                         │
│   Speaker ID (resemblyzer)                                  │
│   TTS (kokoro-onnx + fallback)                              │
└──────────────────────────────┬──────────────────────────────┘
                               │ Bolt / Neo4j
┌──────────────────────────────▼──────────────────────────────┐
│                     Neo4j Graph Database                    │
│   Author · Quote · QuoteOccurrence · Source · Page         │
└─────────────────────────────────────────────────────────────┘
```

The backend is implemented under `backend/app/*`. The frontend communicates with the backend through a centralized API client. Operational data is split between Neo4j, SQLite, and local embedding/audio files.

---

## 4. Step 1 - Wikiquote Graph and Autocomplete

## 4.1 Data Source

The system starts from the official English Wikiquote XML dump:

- `enwikiquote-20251120-pages-articles.xml`

This dump is the raw source from which all graph data is derived.

## 4.2 Parsing and Quote Extraction

The parser is implemented in:

- `backend/app/cli/ingest.py`

It uses `mwparserfromhell` to process MediaWiki markup and extract candidate quotations from:

- quote templates such as `{{quote}}`, `{{cquote}}`, and `{{quotation}}`
- bullet-list quotation sections
- selected article sections likely to contain attributable citations

The extraction pipeline performs:

- page-type classification
- quote validation
- normalization
- deduplication
- attribution cleanup

Each extracted record carries structured fields such as quote text, author, source, page title, page type, normalized text, quote fingerprint, and occurrence key.

## 4.3 Graph Construction

The extracted data is inserted into Neo4j through the maintenance pipeline implemented in:

- `backend/app/cli/maintenance.py`

The graph model uses the following node categories:

- `Author`
- `Quote`
- `QuoteOccurrence`
- `Source`
- `Page`

This design allows one canonical quotation to be connected to multiple occurrences and contexts without duplicating the quote text itself.

## 4.4 Indexing and Search

To satisfy the assignment requirement of autocomplete and retrieval, the system creates full-text indexes over quote-related fields. The search layer supports:

- partial quote matching
- quote autocomplete
- author search
- topic search
- fallback retrieval over a broader quote corpus

The search implementation is centered in:

- `backend/app/integrations/neo4j_quotes.py`
- `backend/app/services/quote_search.py`

The result is a Step 1 system that does not merely store Wikiquote in Neo4j, but actively supports quote completion and attribution.

---

## 5. Step 2 - Interactive Voice System

Step 2 extends the Step 1 graph into an interactive spoken interface.

## 5.1 Automatic Speech Recognition

The ASR module is implemented in:

- `backend/app/integrations/audio/asr.py`

The system uses:

- `mlx-community/whisper-large-v3-turbo`

through `mlx-whisper`. This allows efficient ASR on Apple Silicon without CUDA dependencies.

The ASR output includes:

- the raw transcript
- a normalized transcript for downstream intent handling

## 5.2 Speaker Identification

The speaker-identification module is implemented in:

- `backend/app/integrations/audio/speaker_id.py`

It uses `resemblyzer` to produce speaker embeddings. This directly matches the project instructions that fine-tuning is not required, and that it is sufficient to build a database of embeddings capable of distinguishing users.

The registration path:

- receives multiple user voice samples
- computes a speaker embedding
- stores the embedding for future comparisons

The recognition path:

- computes an embedding for an incoming utterance
- compares it against enrolled users
- returns the highest-scoring match above a configured threshold

## 5.3 Conversational Layer

The conversational module is implemented in:

- `backend/app/services/conversation.py`

This layer is responsible for:

- intent detection
- follow-up management
- routing user input to the quote-search service
- formatting the response text used by the frontend and TTS modules

The approach is rule-based and deterministic, which is appropriate for the narrow task domain of quote lookup and follow-up handling.

## 5.4 Personalized Text-to-Speech

The TTS modules are implemented in:

- `backend/app/integrations/audio/tts.py`
- `backend/app/integrations/audio/tts_fallback.py`

The main TTS engine is `kokoro-onnx`. A per-user voice profile is associated with each registered speaker, allowing different users to hear different synthesized voices. This satisfies the Step 2 requirement that responses should be personalized according to the recognized user's associated voice preferences.

If the primary TTS path is unavailable, the system exposes a fallback TTS path.

---

## 6. Backend Design

The backend is implemented in Python with `FastAPI` and exposed through:

- `backend/app/main.py`

The HTTP layer is structured under:

- `backend/app/api/routers/`
- `backend/app/api/schemas/`
- `backend/app/api/dependencies.py`

Runtime composition is managed through an application container, which owns the long-lived services needed by the system.

The main API route groups are:

- `/api/quotes`
- `/api/authors`
- `/api/chat`
- `/api/voice`
- `/api/users`
- `/api/tts`
- `/api/audio`
- `/api/health`

---

## 7. Frontend

The frontend is implemented with `Next.js` and provides:

- the main conversational interface
- advanced quote-search views
- user registration and management screens
- voice interaction and response playback

---

## 8. Storage Model

The project uses multiple storage layers, each serving a different role.

### Neo4j

Used for:

- quote graph storage
- full-text search indexes
- author/source/page relations
- quote retrieval and autocomplete

### SQLite

Used for:

- user profiles
- TTS preferences
- local metadata for registered users

### Filesystem Storage

Used for:

- speaker embeddings
- generated response audio
- local intermediate data artifacts

---

## 9. End-to-End Flows

## 9.1 Step 1 Flow

```text
Wikiquote XML dump
  → parsing and quote extraction
  → normalized quote records
  → Neo4j population
  → full-text indexing
  → autocomplete and retrieval API
```

## 9.2 Step 2 Voice Query Flow

```text
Browser microphone
  → POST /api/voice/query
  → ASR
  → speaker identification
  → intent parsing
  → quote retrieval
  → natural-language response composition
  → personalized TTS
  → audio playback in browser
```

## 9.3 User Registration Flow

```text
Browser voice samples
  → POST /api/users/register
  → speaker embedding creation
  → user/profile persistence
  → voice assignment and preferences storage
```

---

## 10. Technology Choices and Constraints

The project was developed under practical hardware and software constraints, especially Apple Silicon compatibility.

For that reason:

- `mlx-whisper` was selected for efficient local ASR
- `resemblyzer` was selected for lightweight embedding-based speaker recognition
- `kokoro-onnx` was selected for local text-to-speech without a GPU-specific runtime

---

## 11. Limitations

Although the system is complete and submission-ready, some limitations remain.

- The quote-search layer is primarily lexical and heuristic, not semantic-RAG based.
- The fallback TTS path is less personalized than the main path.
- The backend test suite is currently lightweight and focused on smoke validation rather than exhaustive coverage.

These limitations do not prevent the system from satisfying the course requirements, but they define the main directions for future refinement.

---

## 12. Conclusion

The final system satisfies both mandatory parts of the NLP course project:

- **Step 1**: a Wikiquote graph with indexed autocomplete and attributable quote retrieval
- **Step 2**: a multi-user voice interface with ASR, speaker recognition, conversational querying, and personalized TTS

It combines information extraction, graph-based retrieval, speech technologies, and full-stack integration into a single coherent system aligned with the project instructions.
