# Which Quote?

Which Quote? searches the English Wikiquote dump by voice or by typing. It
completes a quotation you half remember, finds quotations on a subject, lists
what one person said, and reads the answer back in a voice assigned to whoever
is speaking. It was built for a Natural Language Processing course project.

People do not ask for quotations in the words a quotation uses. They misspell,
they ramble, and a microphone adds its own mistakes. So the application makes
one Gemini call per request, and that call turns what the person said into a
typed search intent: which search to run, the words a matching quotation would
itself contain, and a name if one was mentioned. Everything after that is fixed
Cypher against Neo4j.

Gemini never writes a quotation and never writes a query. Every quote and every
attribution on screen comes out of the graph.

## Architecture

```mermaid
flowchart TB
    UI["<b>Browser</b> · Next.js<br/>typing, microphone, playback"]

    ASR["mlx-whisper<br/><i>speech to text</i>"]
    SPK["resemblyzer<br/><i>identifies the speaker</i>"]

    subgraph api["FastAPI process"]
        direction TB
        CONV["<b>ConversationService</b><br/>resolves the user, assembles the reply"]
        WF["<b>QueryWorkflow</b><br/>conversation state, follow-ups"]
        SEARCH["<b>QuoteSearch</b> and repository<br/>one intent, one fixed Cypher query"]
        CONV --> WF --> SEARCH
    end

    SQL[("SQLite<br/>profiles, voice settings")]
    GEM["<b>Gemini 3.5 Flash-Lite</b><br/>one call per request"]
    NEO[("<b>Neo4j</b><br/>quotations, claims, authors")]
    TTS["kokoro-onnx<br/><i>text to speech</i>"]
    WAV[("generated audio<br/>served by /api/audio")]

    UI -->|"spoken"| ASR
    UI -->|"spoken"| SPK
    UI -->|"typed"| CONV
    ASR -->|"transcript"| CONV
    SPK -->|"user id"| CONV
    WF -->|"request in, typed intent out"| GEM
    SEARCH -->|"reads"| NEO
    CONV -->|"reply text"| TTS
    SQL -->|"which voice"| TTS
    TTS --> WAV

    classDef store fill:#eaf5ec,stroke:#3f7a55,color:#17351f
    classDef ext fill:#fdf0e3,stroke:#b5762a,color:#5a3a12
    classDef local fill:#e9ecfa,stroke:#5560a8,color:#22285c
    class NEO,SQL,WAV store
    class GEM ext
    class ASR,SPK,TTS local
```

The reply text, the source, and a link to the audio go back to the browser.

Building the graph is a separate pipeline that runs once. Nothing at request
time writes to Neo4j.

```mermaid
flowchart LR
    XML["Wikiquote XML dump<br/>706 MB"] --> ING["ingest.py<br/><i>streams pages, keeps structure</i>"]
    ING --> NEO[("Neo4j<br/>485,421 quotations")]
    ING -->|"counts each author's quotations"| NEO
```

## What happens on one request

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Web as Next.js
    participant API as FastAPI
    participant Voice as Audio models
    participant LLM as Gemini
    participant DB as Neo4j

    User->>Web: speaks or types<br/>"wat did einstien sya about imaganation"
    Web->>API: POST /api/chat/query or /api/voice/query

    opt spoken
        API->>Voice: transcribe
        Voice-->>API: "what did Einstein say about imagination"
        API->>Voice: match the speaker vector
        Voice-->>API: Amir, 0.89 confident
    end

    API->>LLM: the request, plus the last two for pronouns
    LLM-->>API: kind=topic, terms="imagination knowledge", author="Einstein"

    alt refers to the previous answer
        API->>API: reuse the stored result, no search
    else new subject
        API->>DB: one fixed Cypher query
        DB-->>API: quotations, ranked and one per speaker
    end

    API->>Voice: read the answer in Amir's voice
    Voice-->>API: wav file
    API-->>Web: quotation, author, page, audio link
    Web-->>User: shows the card and plays it
```

## How a request is routed

The rewrite returns a `kind`, and each kind has exactly one query behind it.

| kind | when | query |
| --- | --- | --- |
| `topic` | a subject or feeling | full-text over quotation text, terms optional |
| `topic` with a name | "what did Einstein say about imagination" | the same index, then narrowed to that person |
| `author` | "quotes by Virginia Woolf" | full-text over author names, every name part required |
| `quote_fragment` | wording someone half remembers | punctuation-insensitive substring, then full-text if that misses |
| `random` | no subject given | a random attributed quotation the synthesizer can read |
| `repeat`, `alternative`, `attribution` | the request points at the last answer | no query at all, the workflow reuses what it stored |

Autocomplete uses the fragment query directly and never calls Gemini, so typing
costs nothing and returns instantly.

## The graph

```mermaid
erDiagram
    QUOTE ||--|{ ATTRIBUTION : "HAS_ATTRIBUTION"
    ATTRIBUTION }o--o| AUTHOR : "ATTRIBUTED_TO"

    QUOTE {
        string id "sha256 of the normalised words"
        string text
        string search_text "for substring matching"
    }
    ATTRIBUTION {
        string status "sourced, attributed, disputed, about"
        int status_rank "0 to 3, orders competing claims"
        string citation
        string work_title
        string page_title
    }
    AUTHOR {
        string key "the collapsed lower-case name"
        string name
        int quote_count "weights the text score"
    }
```

The same words can be claimed by different sources, which is why the claim is
its own node: 27,884 quotations carry more than one. `Author` stays a node
because looking up a person is a core query. Work and page titles are only ever
displayed, so they live on the claim instead of becoming two more node types.

## Models and cost

The one model call uses `gemini-3.5-flash-lite`. Google lists it at $0.30 per
million input tokens and $2.50 per million output tokens on the
[pricing page](https://ai.google.dev/gemini-api/docs/pricing).

A rewrite request of 400 input and 50 output tokens costs about $0.000245, so
ten thousand requests cost roughly $2.45. Nothing is charged per quotation,
because the search reads an index the database maintains. Neo4j hosting and
audio compute are not in that figure.

Speech recognition, speaker matching, and synthesis all run locally, so no audio
leaves the machine.

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- Neo4j 2026.01 or newer
- a Gemini API key
- the English Wikiquote pages and articles XML dump

Speech recognition uses `mlx-whisper`, which needs Apple Silicon. Speaker
matching uses `resemblyzer` and synthesis uses `kokoro-onnx`. All three are
optional at runtime: `/api/health` reports which are present, and typed search
works without any of them.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

cd frontend
npm ci
cd ..

cp .env.example .env
```

Set at least these values in `.env`:

```dotenv
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=local-password
GEMINI_API_KEY=...
```

Keep `.env` out of Git and out of any archive you hand in. The application logs
the model name, the intent, token counts, latency, and the fallback reason. It
never logs prompts, audio, keys, or quotation text.

## Build the graph

Start from an empty Neo4j database. Ingestion creates the constraints and
indexes, streams the dump into the graph in batches, and counts each author's
quotations at the end.

```bash
python -m backend.ingest
python -m backend.maintenance verify
```

`verify` prints the current node counts. Search works as soon as the indexes are
online, and there is no separate indexing job to wait for.

For a smaller load while testing:

```bash
PARSE_PAGE_LIMIT=5000 python -m backend.ingest
```

## Run

```bash
uvicorn backend.app:app --reload
```

```bash
cd frontend
npm run dev
```

The API listens on `http://127.0.0.1:8000` and the interface on
`http://127.0.0.1:3000`.

## Enrol a speaker

Registration records at least three samples, averages them into one 256
dimension vector, and assigns an unused Kokoro voice. Recognition compares an
incoming vector against every enrolled one and accepts a match above 0.75.

Record the samples in the room where the system will be used. Measured on two
speakers with a held out sentence, the right speaker scored 0.897 and 0.888
while the two speakers scored 0.578 against each other.

## Test

The suite makes no paid API calls.

```bash
python -m compileall backend
pytest -q

cd frontend
npm test
npm run typecheck
npm run build
```

## Project files

- `backend/app.py`: FastAPI application and routes
- `backend/search.py`: intent routing and the conversation workflow
- `backend/neo4j.py`: graph schema and the fixed queries
- `backend/gemini.py`: the single model call
- `backend/voice.py`: recognition, speaker matching, synthesis
- `backend/users.py`: SQLite profiles and voice settings
- `backend/ingest.py`: the Wikiquote extractor
- `backend/maintenance.py`: graph verification
- `frontend/components/main-shell.tsx`: the text and voice screen
- `REPORT.md`: design and evaluation report

## Contributors

- Amir Hossein Shahdadian
- Mahtab Taheri
- Yasaman Zahedan

See `LICENSE` for licensing information.
