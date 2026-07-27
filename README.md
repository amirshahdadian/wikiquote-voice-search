# Which Quote?

Which Quote? is a Wikiquote search and voice interface built for a Natural
Language Processing course project. It imports the English Wikiquote dump into
Neo4j, completes remembered quote fragments, answers topic and author queries,
and can read results with a voice assigned to an enrolled user.

The application makes one Gemini call per request. That call turns what the user
said into a typed search intent: which kind of search to run, the words to look
for in the quotations themselves, and the person's name when one was mentioned.
Requests arrive misspelled, ungrammatical, or as rough voice transcripts, so the
rewrite is what makes them findable.

Gemini never writes quotations and never produces Cypher. Every quote and every
attribution shown to a user comes from Neo4j.

## Architecture

The graph has three node labels and two relationship types:

```text
(Quote)-[:HAS_ATTRIBUTION]->(Attribution)
                               `--[:ATTRIBUTED_TO]->(Author)
```

`Quote` stores the quotation and its fragment-search form. `Attribution` stores
citation, status, the rank that orders competing claims, work title, and the
Wikiquote page title. This matters because the same words can appear with
different attribution claims. `Author` remains a node because author lookup is a
core query; works and pages are display metadata, so they stay on the
attribution instead of creating two extra node and relationship types.

A query follows a short, fixed workflow:

```text
request -> Gemini rewrite -> Neo4j full-text retrieval -> deterministic response
```

Retrieval is the `quote_text` full-text index, ranked by Lucene. Request terms
are joined with `OR`, because a request never repeats a quotation word for word
and requiring every term returns nothing. When the rewrite also names a person,
the topic results are filtered to that person's attributions. Author and
fragment searches use fixed Cypher queries. Autocomplete is lexical only, so
typing does not make Gemini calls. If Gemini is unavailable, the original
request text is searched unchanged.

One bounded workflow interprets, retrieves, and responds. It cannot choose
tools, create steps, or execute model output. Its local state store keeps one
state for at most 1,000 recently used conversation threads.

Voice transcripts enter this same workflow unchanged. There is no separate
list of filler words, command patterns, or hand-written voice search parser.

## Models and cost

The default model is `gemini-3.5-flash-lite`, used for the one rewrite call.

Google lists Gemini 3.5 Flash-Lite at $0.30 per million input tokens and $2.50
per million output tokens. See the current
[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) before
budgeting.

For a rough example, a rewrite request with 400 input tokens and 50 output
tokens costs about $0.000245. Ten thousand such requests cost about $2.45. There
is no per-quotation indexing cost, because retrieval reads a full-text index the
database maintains. Neo4j hosting, audio processing, taxes, and retry traffic
are not included in these estimates.

Use a Cloud project with active billing for deployed use. Google's
[Gemini API terms](https://ai.google.dev/gemini-api/terms) state that paid
service prompts and responses are not used to improve its products. The terms
also describe limited logging for abuse prevention. Unpaid service data may be
used differently, subject to regional rules. Do not put secrets or unnecessary
personal data in prompts.

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- Neo4j 2026.01 or newer
- a Gemini API key for the request rewrite
- the English Wikiquote pages and articles XML dump

ASR uses `mlx-whisper`, speaker identification uses `resemblyzer`, and TTS uses
`kokoro-onnx`. Voice features are optional at runtime. Text search still works
when an audio model is not installed.

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
GEMINI_LLM_MODEL=gemini-3.5-flash-lite
```

Keep `.env` out of Git. The application logs model name, intent, token counts,
latency, and fallback reason. It does not log prompts, audio, API keys, or full
quotation text.

## Build the graph

Use an empty Neo4j database. Ingestion creates the constraints and indexes, then
streams extracted rows from the XML dump directly into Neo4j in batches.

```bash
python -m backend.ingest
python -m backend.maintenance verify
```

`verify` prints the current graph counts.

For a small validation load:

```bash
PARSE_PAGE_LIMIT=5000 python -m backend.ingest
```

After import, `verify` should report nonzero counts for `Quote`,
`Attribution`, and `Author`. Search works as soon as the indexes are online;
there is no separate indexing job to wait for.

## Run

Start the backend:

```bash
uvicorn backend.app:app --reload
```

Start the frontend in another shell:

```bash
cd frontend
npm run dev
```

The API is at `http://127.0.0.1:8000` and the web interface is at
`http://127.0.0.1:3000`.

Typing three or more characters opens quote completions from the lexical
Neo4j index. This path is debounced in the browser and does not call Gemini.

## Test

The normal test suite makes no paid API calls:

```bash
python -m compileall backend
pytest -q

cd frontend
npm test
npm run typecheck
npm run build
```

## Database cutover

Build and verify the new graph at a separate URI. Point the application to it
only after the live evaluation and application checks pass. Keep the previous
Neo4j store unchanged for seven days. Export or back it up with the standard
Neo4j tools before removing it.

## Project files

- `backend/app.py`: FastAPI application and routes
- `backend/search.py`: retrieval and conversation workflow
- `backend/neo4j.py`: graph schema and fixed queries
- `backend/gemini.py`: typed Gemini boundary
- `backend/voice.py`: speech recognition, speaker matching, and synthesis
- `backend/users.py`: SQLite user profiles and voice settings
- `backend/ingest.py`: structural Wikiquote extraction
- `backend/maintenance.py`: graph verification command
- `frontend/components/main-shell.tsx`: main text and voice interface
- `REPORT.md`: design and evaluation report

## Contributors

- Amir Hossein Shahdadian
- Mahtab Taheri
- Yasaman Zahedan

See `LICENSE` for licensing information.
