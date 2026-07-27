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
classification and embeddings, and a small bounded workflow for conversation
state. The model does not write quotes, generate Cypher, or decide which tools
to run.

## 1. Assignment requirements

The project has two required parts.

Step 1 starts from the official English Wikiquote XML dump, builds a graph
database, adds full-text search, completes partial quotations, and returns their
sources.

Step 2 adds automatic speech recognition, speaker identification from stored
embeddings, conversational querying, and personalized text-to-speech.

The implementation uses:

- `mwparserfromhell` for MediaWiki markup;
- Neo4j 2026.06 for graph storage and search;
- Gemini 3.5 Flash-Lite for intent classification;
- Gemini Embedding 2 for 768-dimensional vectors;
- `mlx-whisper` for speech recognition on Apple Silicon;
- `resemblyzer` for speaker embeddings;
- `kokoro-onnx` for speech synthesis;
- FastAPI and Next.js for the application.

## 2. Data extraction

`backend/ingest.py` streams the XML dump with ElementTree. Page IDs are
used while deriving stable attribution IDs, but only fields used by the graph
are emitted.

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
about, malformed, and duplicate cases. Four more cases use structural markers
from current raw pages for Albert Einstein, Maya Angelou, William Shakespeare,
and Hamlet. The extractor is 486 lines. The prior file was 2,047 lines.

## 3. Graph model

The graph has three labels:

```text
Quote
Attribution
Author
```

It has two relationship types:

```text
(Quote)-[:HAS_ATTRIBUTION]->(Attribution)
(Attribution)-[:ATTRIBUTED_TO]->(Author)
```

`Quote` contains `id`, `text`, `search_text`, `embedding`, `embedding_model`,
and `embedding_dimensions`. `Attribution` contains status, citation, work
title, and Wikiquote page title. These fields describe a claim about a
quotation, not the words themselves. `Author` remains a node because lookup by
author is a core query. Work and page values are display metadata, so separate
nodes and traversals would add structure without supporting another query.

Neo4j constraints make quote IDs, attribution IDs, and author keys unique. Two
full-text indexes cover quote text and author names. A text index handles
punctuation-insensitive fragments. The vector index uses cosine similarity and
768 dimensions.

Ingestion creates the schema and streams extracted rows from the XML dump
directly into Neo4j. The maintenance CLI keeps three explicit commands:

```bash
python -m backend.maintenance schema
python -m backend.maintenance embed
python -m backend.maintenance verify
```

The verification command reports current node counts and quotes with missing
or stale embeddings.

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
author search, autocomplete, and random selection. Model text is never
interpolated into Cypher.

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

The workflow asks Gemini for a typed `SearchIntent`, calls fixed retrieval, and
formats a short response from retrieved fields. Its small in-memory state store
is keyed by conversation ID. Repeat, alternative, and attribution follow-ups
reuse the latest result. Each thread stores eight history messages, and a
least-recently-used cap keeps no more than 1,000 threads in process memory.

This is orchestration, not an autonomous agent. There is no planner loop, tool
catalog, generated query language, or open-ended model response. A more
general agent would add cost and failure modes without helping this task.

## 7. Voice and users

Voice input is transcribed by `mlx-whisper` and passed unchanged to the same
Gemini intent classifier used for typed requests. There is no second
hand-written voice command parser. If the user did not choose a profile,
`resemblyzer` compares the incoming speaker vector with enrolled user
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

The quote API has canonical search and autocomplete endpoints. The frontend
debounces typed fragments and displays lexical suggestions without calling
Gemini. Chat and voice requests share the same workflow, so they cannot drift
into separate search implementations.

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

The offline suite covers extraction, fixed Cypher generation, rank fusion,
workflow follow-ups, API mapping, users, ASR, speaker identification, and TTS.
Live checks use reviewable requests against the imported dump: exact fragments,
author lookup, topic lookup, random selection, attribution follow-up, and a
recorded voice request. This avoids fixed expected quotations that may not
exist in a newer `latest` Wikiquote dump.

## 11. Code reduction

Production Python, TypeScript, TSX, and CSS across the repository fell from
11,924 to 5,914 lines, a reduction of about 50 percent.
Most of the removed code was heuristic classification,
manual relevance scoring, duplicate endpoint logic, and compatibility code for
the old graph.

The remaining code is split at boundaries that can be tested with small fake
clients. Gemini classification, vector embedding, fixed Neo4j queries, rank
fusion, workflow state, and HTTP mapping each have focused tests.

## 12. Cutover procedure

The current Neo4j Desktop graph contains 522,590 quotes, 556,853 attributions,
and 47,062 authors. It has 953,857 relationships: 556,853
`HAS_ATTRIBUTION` edges and 397,004 `ATTRIBUTED_TO` edges. Every attribution
has a page title, all indexes are online, and integrity checks report no blank
or orphan nodes. A stopped Docker volume preserves the pre-cutover graph.

The remaining deployment step is the paid Gemini embedding backfill. Vector
retrieval stays disabled until every quote has the configured model and 768
dimensions; lexical, fragment, and author retrieval remain available.
