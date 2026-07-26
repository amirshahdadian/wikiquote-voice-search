# Which Quote? project report

Natural Language Processing, Data Science Master's degree

Team: Amir Hossein Shahdadian, Mahtab Taheri, Yasaman Zahedan

## Abstract

Which Quote? imports the English Wikiquote dump into Neo4j and provides quote
autocomplete, author lookup, topic search, and a multi-user voice interface.
The first implementation grew around a large deterministic parser and a
hand-written search pipeline. It worked, but its graph mixed canonical quotes
with display fields, and its search logic had become hard to explain or test.

The current design separates quotations from attribution claims. It uses
Neo4j full-text and vector indexes for retrieval, Gemini for typed intent
classification and embeddings, and a three-step LangGraph workflow for
conversation state. The model does not write quotes, generate Cypher, or decide
which tools to run.

## 1. Assignment requirements

The project has two required parts.

Step 1 starts from the official English Wikiquote XML dump, builds a graph
database, adds full-text search, completes partial quotations, and returns their
sources.

Step 2 adds automatic speech recognition, speaker identification from stored
embeddings, conversational querying, and personalized text-to-speech.

The implementation uses:

- `mwparserfromhell` for MediaWiki markup;
- Neo4j 5.26 for graph storage and search;
- Gemini 3.5 Flash-Lite for intent classification;
- Gemini Embedding 2 for 768-dimensional vectors;
- `mlx-whisper` for speech recognition on Apple Silicon;
- `resemblyzer` for speaker embeddings;
- `kokoro-onnx` for speech synthesis;
- FastAPI and Next.js for the application.

## 2. Data extraction

`backend/app/cli/ingest.py` streams the XML dump with ElementTree. It preserves
the Wikiquote page ID and revision ID for every extracted attribution.

The extractor trusts page structure:

- quote templates such as `quote`, `cquote`, and `quotation`;
- top-level bullets followed by attribution sub-bullets;
- `blockquote` elements;
- explicit links for authors and works;
- section headings for sourced, attributed, disputed, and about status.

It excludes non-content namespaces, redirects, and reference sections. It
checks quote length, word count, and alphabetic character ratio. It does not
guess whether arbitrary introductory prose names a person, infer authors from
geography, or maintain an English-language blacklist of sentence patterns.

Quote IDs are SHA-256 hashes of normalized quotation text. Attribution IDs also
include page ID, author, work, status, and citation. Identical words therefore
share one `Quote`, while separate Wikiquote claims remain separate
`Attribution` nodes.

A 20-page golden fixture covers person, theme, literary work, film, disputed,
about, malformed, and duplicate cases. The extractor is 494 lines. The prior
file was 2,047 lines.

## 3. Graph model

The graph has five labels:

```text
Quote
Attribution
Author
Work
WikiquotePage
```

It has four relationship types:

```text
(Quote)-[:HAS_ATTRIBUTION]->(Attribution)
(Attribution)-[:ATTRIBUTED_TO]->(Author)
(Attribution)-[:FROM_WORK]->(Work)
(Attribution)-[:FOUND_ON]->(WikiquotePage)
```

`Quote` contains `id`, `text`, `normalized_text`, `embedding`,
`embedding_model`, and `embedding_dimensions`. Author, work, citation, page,
and status are deliberately absent from the quote node. They describe a claim
about a quotation, not the words themselves.

Neo4j constraints make the IDs and entity keys unique. Two full-text indexes
cover quote text and author names. The vector index uses cosine similarity and
768 dimensions.

The maintenance CLI has four explicit commands:

```bash
python -m backend.app.cli.maintenance schema
python -m backend.app.cli.maintenance load
python -m backend.app.cli.maintenance embed
python -m backend.app.cli.maintenance verify
```

The loader refuses an old database unless the operator supplies the legacy
override. In normal use the new schema is built in an empty database. The
verification command reports current node counts, legacy label counts, and
quotes with missing or stale embeddings.

## 4. Embeddings

Document embeddings use `gemini-embedding-2` with 768 output dimensions. Input
text follows the model's retrieval format:

```text
title: none | text: <quotation>
```

Query embeddings use:

```text
task: search result | query: <request>
```

The backfill uses Gemini's Batch API. Each JSONL row is keyed by the stable
quote ID. One local state file records the active job name, model, dimensions,
and submission time. Repeated `embed` commands poll that job instead of
creating duplicates. Successful results are checked for the expected vector
length before they are written to Neo4j.

## 5. Retrieval

The runtime exposes fixed repository methods for lexical search, vector search,
author search, autocomplete, random selection, and popular authors. Model text
is never interpolated into Cypher.

Topic retrieval runs full-text and vector searches, then combines their ranks
with reciprocal rank fusion. It does not try to compare raw full-text scores
with cosine scores. Quote fragments remain lexical because exact wording is
more useful than semantic similarity for that intent. Autocomplete is also
lexical and never calls Gemini.

Each result follows a `Quote` to one `Attribution`. Sourced claims are preferred
over attributed, disputed, and other claims. Nullable author and work fields
remain null instead of creating fake "Unknown" graph entities.

If the query embedding request fails, the lexical results are returned. If
intent classification fails or no API key is configured, the request becomes a
topic search using the original text. Search therefore remains usable during a
Gemini outage.

## 6. Conversation workflow

LangGraph runs three nodes:

1. `interpret` asks Gemini for a `SearchIntent` schema;
2. `retrieve` calls the fixed hybrid search service;
3. `respond` formats a short response from retrieved fields.

The graph uses an in-memory checkpoint keyed by conversation ID. Repeat,
alternative, and attribution follow-ups reuse prior results. The state keeps
only the recent conversation history.

This is orchestration, not an autonomous agent. There is no planner loop, tool
catalog, generated query language, or open-ended model response. A more
general agent would add cost and failure modes without helping this task.

## 7. Voice and users

Voice input is transcribed by `mlx-whisper`. If the user did not choose a
profile, `resemblyzer` compares the incoming speaker vector with enrolled user
embeddings. The selected or recognized user ID determines the Kokoro voice and
speech preferences.

Kokoro is the only TTS engine. If it cannot initialize or synthesize audio, the
API returns the `tts_unavailable` warning and the text response remains usable.
There is no hidden network fallback.

User metadata and voice preferences are stored in SQLite. Speaker vectors and
generated audio remain local files.

## 8. Application boundary

The FastAPI container owns one Gemini client, one Neo4j driver, and the shared
audio and user services. The two clients are closed during application
shutdown.

The frontend has one main quote interaction screen. It supports text input,
microphone input, selected users, recognized users, related quotations, source
provenance, and audio playback. Registration and user administration have
their own focused routes.

The quote API has canonical search and autocomplete endpoints. Chat and voice
requests share the same workflow, so they cannot drift into separate search
implementations.

## 9. Cost and data handling

At the prices published in July 2026, Gemini 3.5 Flash-Lite costs $0.30 per
million input tokens and $2.50 per million output tokens. Gemini Embedding 2
text input costs $0.20 per million tokens for standard requests and $0.10
through the Batch API. Current prices are published on the
[Gemini API pricing page](https://ai.google.dev/gemini-api/docs/pricing).

An intent request with 200 input tokens and 50 output tokens costs about
$0.000185. At 10,000 requests per month, that is about $1.85. Query embeddings
of 20 tokens each add about $0.04. Backfilling 450,000 quotations averaging 40
to 60 tokens costs about $1.80 to $2.70 through batch processing. These figures
exclude Neo4j and audio compute.

The deployed application should use a Cloud project with active billing.
Google's [Gemini API terms](https://ai.google.dev/gemini-api/terms) say paid
service prompts and responses are not used to improve Google products. The
terms permit limited retention for abuse monitoring. The backend adds its own
metadata-only logs: event, model, intent, latency, token counts, dimensions,
and fallback reason. It does not log prompts, quote text, audio, API keys,
vectors, or model responses.

## 10. Evaluation

The checked-in evaluation corpus contains:

- 40 intent cases;
- 50 exact quotation fragments;
- 20 author queries;
- 40 topic queries with reviewed acceptable quotations.

The acceptance thresholds are 95 percent intent accuracy, 96 percent fragment
recall at five, 95 percent author recall at five, and 85 percent topic recall at
ten. Live tests require `RUN_LIVE_EVALUATION=1`, a Gemini key, and a populated
Neo4j database. The ordinary test suite cannot make paid calls.

A separate opt-in benchmark compares Gemini 3.5 Flash-Lite with Gemini 3.1
Flash-Lite on the 40 intent cases. The configured model changes only if the
cheaper candidate reaches 95 percent and does not lose the author and fragment
distinctions.

The offline suite currently passes. Live retrieval and model thresholds must be
run after the replacement database is populated; this repository does not
pretend that a skipped network test is a quality result.

## 11. Code reduction

The deterministic extraction, search, and conversation group measured 4,027
lines before the redesign. Its direct replacement is 1,653 lines, a reduction
of about 59 percent. Most of the removed code was heuristic classification,
manual relevance scoring, duplicate endpoint logic, and compatibility code for
the old graph.

The remaining code is split at boundaries that can be tested with small fake
clients. Gemini classification, vector embedding, fixed Neo4j queries, rank
fusion, workflow state, and HTTP mapping each have focused tests.

## 12. Cutover procedure

The replacement graph must be built at a separate Neo4j URI. A 5,000-page slice
is imported first, followed by embeddings, verification, live evaluation, and
an application smoke test. The full dump is loaded only after that slice works.

Once the full graph passes the same checks, the application can point to the
new URI. The old Neo4j store stays unchanged for seven days. It is exported or
backed up with standard Neo4j tooling before deletion.

At the time of this report, the local checkout has no running Neo4j service and
no Gemini API key. The code, offline tests, typecheck, and frontend production
build can be verified locally. Database counts, paid model accuracy, and final
cutover remain deployment steps and are reported as such.
