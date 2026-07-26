# Which Quote?

Which Quote? is a Wikiquote search and voice interface built for a Natural
Language Processing course project. It imports the English Wikiquote dump into
Neo4j, completes remembered quote fragments, answers topic and author queries,
and can read results with a voice assigned to an enrolled user.

The application uses Gemini for two narrow jobs:

1. classify a request into a typed search intent;
2. create query and document embeddings.

Gemini never writes quotations and never produces Cypher. Every quote and every
attribution shown to a user comes from Neo4j.

## Architecture

The graph has five node labels and four relationship types:

```text
(Quote)-[:HAS_ATTRIBUTION]->(Attribution)
                               |--[:ATTRIBUTED_TO]->(Author)
                               |--[:FROM_WORK]->(Work)
                               `--[:FOUND_ON]->(WikiquotePage)
```

`Quote` stores only the quotation and its embedding. `Attribution` stores
citation, status, locator, year, and section. This matters because the same
words can appear on several Wikiquote pages with different attribution claims.
Page and revision IDs are kept so an imported statement can be traced back to
the dump.

A query follows a short, fixed workflow:

```text
request -> Gemini intent -> Neo4j retrieval -> deterministic response
```

Topic searches combine Neo4j full-text and vector results with reciprocal rank
fusion. Author and fragment searches use fixed Cypher queries. Autocomplete is
lexical only, so typing does not make Gemini calls. If Gemini is unavailable,
topic search still returns full-text results.

LangGraph holds conversation state and runs three nodes: `interpret`,
`retrieve`, and `respond`. It is a bounded workflow, not an autonomous agent.
It cannot choose tools, create new steps, or execute model output.

## Models and cost

The default model IDs are:

- `gemini-3.5-flash-lite` for intent classification
- `gemini-embedding-2` at 768 dimensions for retrieval

Google lists Gemini 3.5 Flash-Lite at $0.30 per million input tokens and $2.50
per million output tokens. Gemini Embedding 2 costs $0.20 per million text
tokens for normal requests and $0.10 per million text tokens through the Batch
API. See the current [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
before budgeting.

For a rough example, an intent request with 200 input tokens and 50 output
tokens costs about $0.000185. Ten thousand such requests cost about $1.85.
Query embeddings add roughly $0.04 if each query is 20 tokens. A one-time
backfill of 450,000 quotations averaging 40 to 60 tokens costs about $1.80 to
$2.70 through the Batch API. Neo4j hosting, audio processing, taxes, and retry
traffic are not included in these estimates.

Use a Cloud project with active billing for deployed use. Google's
[Gemini API terms](https://ai.google.dev/gemini-api/terms) state that paid
service prompts and responses are not used to improve its products. The terms
also describe limited logging for abuse prevention. Unpaid service data may be
used differently, subject to regional rules. Do not put secrets or unnecessary
personal data in prompts.

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- Neo4j 5.26 or newer
- a Gemini API key for intent classification and embeddings
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
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_EMBEDDING_DIMENSIONS=768
```

Keep `.env` out of Git. The application logs model name, intent, token counts,
latency, and fallback reason. It does not log prompts, audio, API keys,
embeddings, or full quotation text.

## Build the graph

Use an empty Neo4j database. The loader refuses a database containing legacy
`QuoteOccurrence`, `Source`, `PrimaryQuote`, or `SecondaryQuote` labels.

```bash
python -m backend.app.cli.ingest
python -m backend.app.cli.maintenance schema
python -m backend.app.cli.maintenance load
python -m backend.app.cli.maintenance embed
python -m backend.app.cli.maintenance verify
```

The four maintenance commands are:

- `schema`: create constraints plus full-text and vector indexes;
- `load`: import `data/extracted_quotes.json`;
- `embed`: submit, poll, or import one resumable Gemini batch;
- `verify`: print current, legacy, and stale embedding counts.

The `embed` command stores only the batch job name and model metadata under
`artifacts/embeddings/current-job.json`. Run the same command again to poll a
pending job. When a job succeeds, the command imports vectors in batches and
removes the state file. It does not submit another job while one is active.

For a small validation load:

```bash
PARSE_PAGE_LIMIT=5000 python -m backend.app.cli.ingest
python -m backend.app.cli.maintenance schema
python -m backend.app.cli.maintenance load
python -m backend.app.cli.maintenance embed
```

After import, `verify` should report nonzero counts for `Quote`,
`Attribution`, `Author`, `Work`, and `WikiquotePage`. Legacy label counts and
`quotes_without_current_embedding` should all be zero.

## Run

Start the backend:

```bash
uvicorn backend.app.main:app --reload
```

Start the frontend in another shell:

```bash
cd frontend
npm run dev
```

The API is at `http://127.0.0.1:8000` and the web interface is at
`http://127.0.0.1:3000`.

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

The live quality gate requires a populated Neo4j database and explicit opt-in:

```bash
RUN_LIVE_EVALUATION=1 pytest -m integration \
  backend/tests/test_search_evaluation.py -q
```

The two-model intent benchmark is separate because it makes 80 paid model
requests:

```bash
RUN_MODEL_BENCHMARK=1 pytest -m integration \
  backend/tests/test_search_evaluation.py::test_intent_model_price_benchmark -q
```

Keep `gemini-3.5-flash-lite` unless the cheaper candidate reaches at least 95
percent intent accuracy without losing author and quote-fragment distinctions.

## Database cutover

Build and verify the new graph at a separate URI. Point the application to it
only after the live evaluation and application checks pass. Keep the previous
Neo4j store unchanged for seven days. Export or back it up with the standard
Neo4j tools before removing it.

## Project files

- `backend/app/cli/ingest.py`: structural Wikiquote extraction
- `backend/app/cli/maintenance.py`: schema, load, embedding, and verification
- `backend/app/integrations/neo4j_repository.py`: fixed graph queries
- `backend/app/integrations/gemini.py`: typed Gemini boundary
- `backend/app/services/query_workflow.py`: bounded conversation workflow
- `frontend/components/main-shell.tsx`: main text and voice interface
- `REPORT.md`: design and evaluation report

## Contributors

- Amir Hossein Shahdadian
- Mahtab Taheri
- Yasaman Zahedan

See `LICENSE` for licensing information.
