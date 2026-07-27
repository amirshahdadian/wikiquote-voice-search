# Which Quote? project report

Natural Language Processing, Data Science Master's degree

Team: Amir Hossein Shahdadian, Mahtab Taheri, Yasaman Zahedan

## Abstract

Which Quote? imports the English Wikiquote dump into Neo4j and provides quote
autocomplete, author lookup, topic search, and a multi-user voice interface.
The first implementation grew around a large deterministic parser and a
hand-written search pipeline. It worked, but its graph mixed canonical quotes
with display fields, and its search logic had become hard to explain or test.

The current design separates quotations from attribution claims. Retrieval is
the Neo4j full-text index. One Gemini call per request rewrites what the user
said into a typed search intent, and a small bounded workflow keeps conversation
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
- Gemini 3.5 Flash-Lite for the request rewrite;
- `mlx-whisper` for speech recognition on Apple Silicon;
- `resemblyzer` for speaker embeddings;
- `kokoro-onnx` for speech synthesis;
- FastAPI and Next.js for the application.

## 2. System architecture

The browser handles typing, the microphone, and playback. `ConversationService`
resolves the user and assembles the reply, `QueryWorkflow` keeps conversation
state and answers follow-ups from it, and `QuoteSearch` sends one intent to one
fixed Cypher query. Speech recognition, speaker matching, and synthesis run on
the machine, so no audio leaves it. Gemini is the only network call. Neo4j holds
the graph, SQLite holds profiles and voice settings, and generated audio is
written to disk.

The container holds one Gemini client and one Neo4j driver for the life of the
process, and closes both at shutdown. Typed and spoken requests meet at
`ConversationService`, so the two cannot drift into separate search behaviour.
Building the graph is a separate pipeline that runs once, and nothing at request
time writes to Neo4j.

A request moves through five stages. A spoken one is transcribed and its
speaker matched. The text and the previous two requests go to Gemini, which
returns the typed intent. A follow-up is answered from stored state, and
anything else runs one fixed query. The reply is synthesised in the recognised
user's voice. The quotation, its source, and the audio link return together.

## 3. Data extraction

`backend/ingest.py` streams the XML dump with ElementTree. Page IDs are
used while deriving stable attribution IDs, but only fields used by the graph
are emitted.

The extractor trusts page structure:

- quote templates such as `quote`, `cquote`, and `quotation`;
- top-level bullets followed by attribution sub-bullets;
- `blockquote` elements;
- explicit links for authors and works;
- section headings for sourced, attributed, disputed, and about status.

It excludes non-content namespaces, redirects, reference sections, and the cast
and character lists of film and play pages, whose bullets otherwise parse as
quotations: 37,169 rows of the form "Actor - Character" were removed from an
earlier import. It checks quote length, word count, and alphabetic character
ratio. It does not
guess whether arbitrary introductory prose names a person, infer authors from
geography, or maintain an English-language blacklist of sentence patterns.

Quote IDs are SHA-256 hashes of normalized quotation text. Attribution IDs also
include page ID, author, work, status, and citation. Identical words therefore
share one `Quote`, while separate Wikiquote claims remain separate
`Attribution` nodes.

A 20-page golden fixture covers person, theme, literary work, film, disputed,
about, malformed, and duplicate cases. Four more cases use structural markers
from current raw pages for Albert Einstein, Maya Angelou, William Shakespeare,
and Hamlet. The extractor is 487 lines. The prior file was 2,047 lines.

## 4. Graph model

```text
(Quote)-[:HAS_ATTRIBUTION]->(Attribution)-[:ATTRIBUTED_TO]->(Author)
```

The last edge is optional, because 22 percent of claims name no author.

`Quote` contains `id`, `text`, and `search_text`. `Attribution` contains status,
its stored preference rank, citation, work title, and Wikiquote page title.
These fields describe a claim about a quotation, not the words themselves.

`Author` remains a node because lookup by author is a core query, and it is
keyed by its own collapsed, lower-cased name so the graph reads plainly in
Neo4j Browser. Work and page values are display metadata, so separate nodes and
traversals would add structure without supporting another query.

Neo4j constraints make quote IDs, attribution IDs, and author keys unique. Two
full-text indexes cover quote text and author names. A text index handles
punctuation-insensitive fragments.

Ingestion creates the schema and streams extracted rows from the XML dump
directly into Neo4j, creating the constraints and indexes itself, so the
maintenance CLI keeps one command:

```bash
python -m backend.maintenance verify
```

It reports current node counts.

## 5. The request rewrite

An earlier version of this project planned to embed all of the quotations and
fuse vector results with full-text results. That backfill was never run, so the
vector path never executed, and the words a person says when asking for a quote
were sent to the full-text index unchanged. Every term was required, which made
the frequent case return nothing at all:

| request | old retrieval | current retrieval |
| --- | --- | --- |
| "wat did einstein say about imaginaton" | no results | Einstein on imagination and knowledge |
| "how do i be brave when i am scared" | no results | Twain on courage as mastery of fear |
| "i wanna know sumthing about how ur mistakes make u learn better" | no results | "Mistakes are valuable lessons often learned too late." |

The one Gemini call per request now returns three fields instead of one. `kind`
is the search to run. `search_text` holds the words a matching quotation would
itself contain, spelled correctly, with filler and question words dropped and
close synonyms added; for a remembered fragment it stays verbatim, because exact
wording is the point of that intent. `author` holds a person's name when a topic
request also mentions one.

The rewrite is a schema-constrained response, so the model returns fields, never
Lucene and never Cypher. Query terms are still stripped of Lucene operators
before they reach the index. If the rewrite fails or no API key is configured,
the original request text is searched unchanged, so the system degrades to the
behaviour it had before rather than to an error.

Removing embeddings deleted the batch submission and polling code, the vector
index, the stored vectors, the rank fusion, the embedding settings, and the
`embed` command: about 300 lines, and the entire per-quotation indexing cost.

## 6. Retrieval

The runtime exposes fixed repository methods for lexical search, author-filtered
topic search, author search, fragment search, autocomplete, and random
selection. Model text is never interpolated into Cypher.

Topic retrieval reads the `quote_text` full-text index and takes Lucene's
ranking. Terms are joined with `OR`: a request never repeats a quotation word
for word, so requiring every term is what produced the empty results above, and
Lucene already weights rare words above common ones. When the rewrite names a
person, the same index is read and then filtered to that person's attributions,
which separates Einstein's own words from the many quotations that merely
mention him.

Lucene scores term density, so a ten-word quotation repeating two search words
outranks a famous one that names its subject once. Asked for courage, the index
returned "Cowardice, when done correctly, can be its own kind of bravery" first
and placed Mark Twain's "Courage is resistance to fear" 592nd. Neo4j exposes no
BM25 length parameter, only the analyzer, so the correction is applied after the
index rather than inside it: the text score is multiplied by how much Wikiquote
holds of the speaker, saturating as `weight / (100 + weight)` so that a prolific
author cannot outweigh relevance itself. Ingestion counts each author's
quotations once and stores the number on the `Author` node.

Two candidate signals were measured before choosing. How many pages cite a
quotation turned out to be useless, because 457,537 of 485,421 quotations are
cited exactly once, Twain's included. How many quotations an author has
separates them clearly: Shakespeare 2,726 and Twain 348 against 6 for the author
that outranked him. Topic results then keep one quotation per speaker, so a
prolific author cannot fill the page. The top five for courage changed from four
unknown writers to Montaigne, Shakespeare and La Rochefoucauld, and Twain's line
now answers "me want quote about brave" directly. Retrieval costs about 90 ms
more per topic search, against a request already dominated by the model call.

Each result follows a `Quote` to one `Attribution`. Nullable author and work
fields remain null instead of creating fake "Unknown" graph entities.

Choosing that one attribution is the only part of retrieval that is not a
straight lookup, because 27,884 quotations carry more than one claim. The
preference order is stored: ingestion writes `Attribution.status_rank`, 0 for
sourced through 3 for anything else, so every query orders by one integer
property instead of evaluating a four-branch `CASE` at read time. The ranking
changes the answer for 2,444 quotations, which is why it is kept and why it is
cheap.

There are then two query shapes, one per way of reaching a quotation. Text
searches arrive with no claim in hand and call a subquery that picks the
quotation's best claim. Author searches already hold the claim that matched the
author, so they order and take the first with `head(collect(...))` and share a
single result clause. Neither shape walks the attribution path twice.

## 7. Conversation workflow

The workflow asks Gemini for a typed `SearchIntent`, calls fixed retrieval, and
formats a short response from retrieved fields. Its small in-memory state store
is keyed by conversation ID. Repeat, alternative, and attribution follow-ups
reuse the latest result. Each thread stores eight history messages, and a
least-recently-used cap keeps no more than 1,000 threads in process memory.

Because the follow-up results come from that store rather than from the model,
the model only has to name the kind of the current utterance. The prompt
therefore labels the current request apart from the two earlier ones, which are
present only to resolve words like "he" or "that". An unlabelled history was
enough to make a new subject read as another follow-up: after "who said that?"
and "repeat that", a fresh request about learning from mistakes came back as
`repeat` and returned the previous quotation.

This is orchestration, not an autonomous agent. There is no planner loop, tool
catalog, generated query language, or open-ended model response. A more
general agent would add cost and failure modes without helping this task.

## 8. Voice and users

Voice input is transcribed by `mlx-whisper` and passed unchanged to the same
Gemini rewrite used for typed requests. There is no second hand-written voice
command parser. Transcription errors and spoken filler are handled by the
rewrite, not by a list of stop words. If the user did not choose a profile,
`resemblyzer` compares the incoming speaker vector with enrolled user
embeddings. The selected or recognized user ID determines the Kokoro voice and
speech preferences.

Kokoro is the only TTS engine. If it cannot initialize or synthesize audio, the
API returns the `tts_unavailable` warning and the text response remains usable.
There is no hidden network fallback.

User metadata and voice preferences are stored in SQLite. Speaker vectors and
generated audio remain local files.

Identification was measured with two enrolled speakers and a held-out utterance
neither enrollment had seen. The correct speaker scored 0.897 and 0.888 while the
two speakers scored 0.578 against each other, so the 0.75 threshold separates
them with room on both sides. The two speaker vectors currently committed under
`data/embeddings` do not meet that standard: they score 0.708 against each other,
which is higher than a genuine recording of one of those speakers scores against
their own vector. They predate the current enrollment flow and have to be
recorded again through registration before a live demo.

## 9. Application boundary

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

## 10. Cost and data handling

At the prices published in July 2026, Gemini 3.5 Flash-Lite costs $0.30 per
million input tokens and $2.50 per million output tokens. Current prices are
published on the
[Gemini API pricing page](https://ai.google.dev/gemini-api/docs/pricing).

A rewrite request with 400 input tokens and 50 output tokens costs about
$0.000245. At 10,000 requests per month, that is about $2.45. Nothing is charged
per quotation, because the index the search reads is maintained by the database.
These figures exclude Neo4j and audio compute.

The deployed application should use a Cloud project with active billing.
Google's [Gemini API terms](https://ai.google.dev/gemini-api/terms) say paid
service prompts and responses are not used to improve Google products. The
terms permit limited retention for abuse monitoring. The backend adds its own
metadata-only logs: model, intent, latency, token counts, and fallback reason. It
does not log prompts, quote text, audio, API keys, or model responses.

## 11. Evaluation

The offline suite is 89 tests over extraction, fixed Cypher generation, the
rewrite contract, intent routing, workflow follow-ups, API mapping, users, ASR,
speaker identification, and TTS. Several of them exist to hold a boundary rather
than to check an output: one fails if any read query evaluates a `CASE` or walks
the attribution path twice, and it caught a regression while the random query was
being rewritten. The frontend adds five component tests.

The live checks run against the imported dump and the real model rather than
against fixed expected quotations, which may not exist in a newer `latest` dump.
They cover the rewrite on misspelled and ungrammatical requests, each intent
kind, a ten-turn conversation mixing new subjects with repeat, alternative, and
attribution follow-ups, fragment completion, autocomplete, and all fifteen HTTP
endpoint behaviours including the audio path traversal guard.

Twenty-three prompts were then run against the live graph and the real model,
chosen to break the rewrite rather than flatter it: heavy misspelling, broken
grammar, an indirect reference to an author by their book, a request in Spanish,
an instruction to ignore the instructions, and pure keyboard noise. Every one was
classified correctly. The rewrite reconstructed "all the world's a stage" from a
vague description, resolved "the guy who wrote 1984" to Orwell, answered the
Spanish request from the English graph, and returned typed fields rather than
prose when told to write a poem. Three faults surfaced that no unit test could
have found, and section 3, section 6 and section 8 record what they were.

The voice path was closed end to end by synthesizing a spoken question with
Kokoro, posting the audio to the voice endpoint, and confirming that
`mlx-whisper` returned the sentence, that the rewrite routed it to the
author-filtered search, and that the reply came back with generated audio.

## 12. Code reduction

Production Python, TypeScript, TSX, and CSS across the repository fell from
11,924 to 4,946 lines, a reduction of about 59 percent. Most of the removed code
was heuristic classification, manual relevance scoring, duplicate endpoint logic,
compatibility code for the old graph, and the embedding pipeline that the
rewrite replaced.

The remaining code is split at boundaries that can be tested with small fake
clients. The rewrite contract, fixed Neo4j queries, intent routing, workflow
state, and HTTP mapping each have focused tests.

## 13. Cutover procedure

The current Neo4j Desktop graph contains 485,421 quotes, 518,770 attributions,
and 47,062 authors. It has 915,768 relationships: 518,770
`HAS_ATTRIBUTION` edges and 396,998 `ATTRIBUTED_TO` edges. Every attribution
has a page title, all indexes are online, and integrity checks report no blank
or orphan nodes. A stopped Docker volume preserves the pre-cutover graph.

There is no remaining indexing step. Retrieval works against the graph as
imported, and the only deployment requirement is a Gemini API key for the
rewrite. Without one, requests are searched as typed.
