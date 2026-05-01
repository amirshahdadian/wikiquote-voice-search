# NLP Pipeline Report

This document extracts the NLP-related work implemented in this project, from the raw data source to the final voice-interactive system.

---

## 1. Project Scope

The repository implements two connected NLP tasks:

1. **Step 1**: build a citation autocomplete and retrieval system over the English Wikiquote dump using a graph database.
2. **Step 2**: build a multi-user voice interface over Step 1 with:
   - automatic speech recognition
   - speaker identification based on stored voice embeddings
   - conversational query handling
   - personalized text-to-speech

The final system is implemented in:

- backend runtime: `backend/app/*`
- frontend runtime: `frontend/*`

The NLP core is almost entirely on the backend side.

---

## 2. High-Level NLP Flow

```text
Official Wikiquote XML dump
  → MediaWiki parsing and quote extraction
  → normalization, validation, deduplication
  → Neo4j graph construction
  → full-text indexing
  → quote autocomplete / retrieval / author / theme search
  → conversational interface over search results
  → voice input transcription
  → speaker recognition
  → personalized natural-language answer
  → personalized text-to-speech output
```

---

## 3. NLP Components By Stage

## 3.1 Data Source and Corpus Construction

### Source

The system starts from the official English Wikiquote dump:

- `enwikiquote-20250601-pages-articles.xml`

This is the raw corpus used to build the knowledge graph.

### Implemented in

- `backend/app/cli/ingest.py`

### NLP work performed

- MediaWiki parsing with `mwparserfromhell`
- quote candidate extraction from structured wiki markup
- page classification
- quote cleaning and normalization
- quote validation
- quote deduplication
- attribution cleanup

This stage is the core information-extraction step of the project.

---

## 3.2 Quote Extraction Logic

The parser recognizes multiple Wikiquote quotation forms.

### Extracted structures

- quote templates such as:
  - `{{quote}}`
  - `{{cquote}}`
  - `{{quotation}}`
  - `{{bquote}}`
  - `{{rquote}}`
  - `{{quote box}}`
  - `{{centered pull quote}}`
  - `{{pull quote}}`
- quotation bullet lists
- section-based quote regions

### Excluded sections

The parser explicitly excludes sections that are usually unreliable or non-citation material, including:

- references
- external links
- bibliography
- misattributed
- disputed
- quotes about
- dubious
- unverified

This is important because it acts as a knowledge-source filtering stage before graph insertion.

---

## 3.3 Page Classification

Each Wikiquote page is classified into a page type before quote extraction and ranking.

### Main page types

- `person`
- `literary_work`
- `film`
- `tv_show`
- `theme`
- `calendar_day`
- `compilation_page`

### Why this matters

Page type influences:

- extraction behavior
- filtering rules
- maximum quotes per page
- ranking multipliers during search

So page classification is not just metadata. It directly affects both corpus quality and downstream retrieval.

---

## 3.4 Text Validation and Filtering

Extracted quotes go through a validation gate.

### Validation dimensions

- minimum character length
- maximum character length
- minimum word count
- maximum word count
- maximum sentence count
- minimum alphabetic ratio

### Configured constraints

These are controlled through backend settings:

- `quote_min_length`
- `quote_max_length`
- `quote_min_words`
- `quote_max_words`
- `quote_max_sentences`
- `quote_min_alpha_ratio`

### NLP purpose

This stage removes:

- transcript filler
- very short non-quotable utterances
- noisy malformed text
- punctuation-heavy junk
- low-information strings

It serves as quality control before graph population.

---

## 3.5 Normalization and Deduplication

Normalization happens at multiple points in the system.

### Quote-level normalization

The parser computes:

- canonical quote text
- normalized quote text
- fingerprint hashes
- occurrence keys

### Search normalization

In search, text normalization includes:

- Unicode decomposition
- diacritic removal
- lowercase conversion
- symbol cleanup
- punctuation stripping
- whitespace normalization
- `&` normalization to `and`

### Deduplication strategy

The parser deduplicates quotes through:

- quote fingerprints for canonical quote identity
- occurrence keys for page/source-level occurrence identity

### NLP role

This prevents duplicate matches from dominating retrieval and makes autocomplete behave more like citation retrieval rather than page-text matching.

---

## 3.6 Parser Improvements Made During The Project

The parser was substantially improved over an earlier, much noisier version.

### Key improvements

- film and TV pages were reduced to **tagline-focused extraction**
- colon-prefixed transcript dialogue was suppressed for `film` and `tv_show`
- per-page quote caps were introduced
- translation detection was tightened to explicit translation markers
- deduplication keys were simplified to reduce near-duplicate occurrences
- redundant `source_locator` duplication was removed
- literary-work pages no longer use the work title as a fake author
- film/TV title detection was broadened to catch titles like `(2004 film)` and `(1981 TV series)`
- theme pages now require attribution sub-bullets before emitting quotes

### Corpus effect

According to `PARSER_IMPROVEMENTS.md`, the corpus moved from roughly:

- **1.3M extracted rows**

to:

- **364,017 cleaned quotes**

This is one of the most important NLP improvements in the entire project because it directly improved retrieval quality.

---

## 3.7 Knowledge Graph Construction

The extracted quote data is loaded into Neo4j.

### Implemented in

- `backend/app/cli/maintenance.py`

### Main graph node types

- `Author`
- `Quote`
- `QuoteOccurrence`
- `Source`
- `Page`

### NLP value of the graph

The graph structure preserves:

- quote text
- attribution
- source
- page context
- occurrence-level metadata

This allows the system to move beyond flat string matching and support attribution-aware retrieval.

---

## 3.8 Full-Text Indexing

The project creates Neo4j full-text indexes for retrieval and autocomplete.

### Main indexes

- `quote_primary_fulltext_index`
- `quote_fulltext_index`

### Search scopes

The system distinguishes between:

- a **primary corpus**
- a **secondary/broader corpus**

The primary corpus favors higher-quality sourced content and is searched first. The broader corpus is used for backfilling and fallback retrieval.

### NLP purpose

This supports:

- quote autocomplete
- lexical phrase search
- citation completion
- fallback retrieval when exact matches are sparse

---

## 3.9 Quote Search and Retrieval

The main search engine is implemented in:

- `backend/app/integrations/neo4j_quotes.py`
- wrapped by `backend/app/services/quote_search.py`

### Supported retrieval modes

- full-text quote search
- keyword search
- fuzzy lexical search
- partial quote completion
- author search
- fuzzy author search
- theme search
- autocomplete
- voice-optimized search
- random quote retrieval
- popular-author retrieval

### Search pipeline behavior

The general pipeline is:

1. primary full-text search
2. primary keyword search
3. primary fuzzy search
4. secondary full-text search
5. secondary keyword search
6. secondary fuzzy search

Results are deduplicated across strategies.

### Partial quote detection

The system distinguishes partial quote fragments from natural-language commands. This is important because:

- `"to be or not"` should behave like a quote completion query
- `"quotes about courage"` should behave like topic search

This is a lightweight intent-routing task inside the retrieval layer itself.

---

## 3.10 Retrieval Scoring

The search engine uses handcrafted ranking logic rather than a learned reranker.

### Full-text scoring factors

The implemented ranking combines:

- base Lucene/Neo4j full-text score
- quote length preference
- query coverage ratio
- source availability bonus
- quote type bonus
- position bonus
- prefix-gap bonus
- page-type multiplier

### Partial quote scoring

Partial quote completion uses an additive scoring model with signals such as:

- exact match
- starts-with match
- word-boundary match
- substring match
- completion length
- query coverage
- prefix distance
- quote type
- source presence
- page type

### Author search scoring

Author search prioritizes:

- exact match
- prefix match
- word-boundary match
- partial contains match
- fuzzy fallback for misspellings

### NLP interpretation

This is a classic rule-based ranking system:

- no embedding reranker
- no neural semantic retriever
- fully interpretable
- tailored to citation retrieval quality

---

## 3.11 Theme Search and Lexical Expansion

The search layer contains a small hand-built theme lexicon.

### Example themes

- love
- wisdom
- life
- success
- happiness
- peace
- death
- friendship
- freedom
- truth
- courage
- justice

Each theme expands to a small set of related lexical terms. This is effectively a lightweight semantic expansion mechanism implemented without embeddings.

---

## 3.12 Autocomplete

Autocomplete is implemented as a thin variant of quote search with fuzzy matching disabled.

### NLP behavior

- favors fast lexical matches
- avoids unnecessary fuzzy drift
- supports partial user input
- returns short suggestion lists suitable for interface use

This is the final form of Step 1 as required in the assignment.

---

## 3.13 Voice-Oriented Search

The project includes a dedicated `voice_search` mode.

### What it does

- uses the standard quote search pipeline
- limits result count
- truncates long quotes for spoken delivery

This is a bridge between Step 1 retrieval and Step 2 voice response generation.

---

## 3.14 Automatic Speech Recognition

The ASR component is implemented in:

- `backend/app/integrations/audio/asr.py`

### Model

- `mlx-community/whisper-large-v3-turbo`

### Backend

- `mlx-whisper`

### Implemented ASR-related NLP logic

- transcription of uploaded speech audio
- domain prompt injection through `_INITIAL_PROMPT`
- extraction of raw transcript text
- generation of a normalized command transcript

### Command normalization

The ASR post-processing includes:

- correction of common mishearings of the word `"quotes"` such as:
  - `codes`
  - `coats`
  - `courts`
  - `cords`
- filler-word removal:
  - `um`
  - `uh`
  - `like`
  - `you know`
  - `i mean`
  - `so`
  - `well`
  - `okay`
  - `alright`
  - `actually`
- normalization of command phrases such as:
  - `find me some` → `find`
  - `can you find` → `find`
  - `search for` → `find`
  - `look for` → `find`

Then stop-like command words are removed to leave the core query topic when possible.

### NLP role

This is not just ASR. It is ASR plus query cleanup for downstream retrieval.

---

## 3.15 Speaker Identification

The speaker recognition component is implemented in:

- `backend/app/integrations/audio/speaker_id.py`

### Model family

- `resemblyzer`

### Implemented speaker-embedding pipeline

- audio preprocessing
- embedding extraction
- multi-sample enrollment
- averaged speaker representation
- cosine-similarity scoring
- threshold-based identification

### Technical properties

- embedding size: **256 dimensions**
- embedding type: L2-normalized float32 vector
- matching metric: cosine similarity
- default decision threshold: **0.75**

### Enrollment behavior

For registration, multiple clips are:

- preprocessed
- embedded
- averaged into one speaker embedding
- saved as a `.pkl` file

### Identification behavior

At query time:

- the incoming clip is embedded
- it is compared to all enrolled users
- the best match is accepted only if similarity exceeds threshold

### NLP role

This is the user identity modeling component of the voice system. It is not semantic NLP, but it is one of the core speech-intelligence modules requested in Step 2.

---

## 3.16 User Registration and Voice Personalization

The user-management layer is implemented in:

- `backend/app/services/users.py`

### NLP-adjacent functions

- requires at least 3 audio samples per user
- creates and stores the speaker embedding
- associates each user with TTS preferences
- assigns a unique Kokoro voice style where possible

### Identity normalization

Display names are converted to user IDs using slugification:

- lowercase conversion
- non-alphanumeric collapse to `-`

This is a simple but useful normalization step for identity management.

---

## 3.17 Conversation and Intent Parsing

The conversational layer is implemented in:

- `backend/app/services/conversation.py`

### Intent parser

The project uses a rule-based `IntentParser`.

### Main supported intents

- `topic_search`
- `author_search`
- `quote_lookup`
- `repeat`
- `follow_up_attribution`
- `follow_up_alternative`

### Example pattern types

- `"who said ..."` / `"who wrote ..."` → quote lookup
- `"quotes about courage"` → topic search
- `"what did Einstein say"` → author search
- `"repeat"` → replay last answer
- `"who said that"` → attribution follow-up
- `"another one"` → next result follow-up

### Conversation state

The system keeps:

- conversation ID
- limited dialogue history
- last query
- last result set
- last response text
- last intent
- current index into alternative results

### NLP role

This is the dialogue-management layer that turns raw transcript text into task-specific retrieval actions.

---

## 3.18 Response Generation

The conversation service also generates answer text.

### Output style

Responses are template-based, not LLM-generated.

Examples of generated response forms:

- quote about topic
- quote by author
- attribution explanation
- repeat of prior result
- alternative quote from previous result set

### NLP interpretation

This is a narrow-domain natural-language generation layer based on templates and structured quote metadata.

---

## 3.19 Personalized Text-to-Speech

The TTS system is implemented in:

- `backend/app/integrations/audio/tts.py`
- `backend/app/integrations/audio/tts_fallback.py`

### Main TTS model

- `kokoro-onnx`

### Personalization logic

Each user can have:

- `style` (voice preset)
- `speaking_rate`
- `pitch_scale`
- `energy_scale`

The main engine uses the stored user voice preset and speaking rate. The system includes a predefined pool of Kokoro voices and tries to assign unique voices across users before recycling.

### NLP role

TTS is the final natural-language realization stage of the system. It converts the structured response text into audible output personalized to the recognized or selected user.

---

## 3.20 Backend API As NLP Orchestration Layer

The FastAPI layer exposes the NLP pipeline through route groups such as:

- `/api/quotes`
- `/api/authors`
- `/api/chat`
- `/api/voice`
- `/api/users`
- `/api/tts`

This turns the implemented NLP components into an end-to-end service pipeline consumable by the frontend.

---

## 4. End-to-End NLP Pipeline

## 4.1 Step 1 End-to-End

```text
Wikiquote XML
  → MediaWiki parsing
  → quote extraction
  → validation
  → normalization
  → deduplication
  → graph population in Neo4j
  → full-text indexing
  → autocomplete / quote retrieval / author search / theme search
```

## 4.2 Step 2 End-to-End

```text
User voice input
  → ASR transcription
  → transcript normalization
  → speaker embedding extraction
  → speaker matching
  → intent parsing
  → quote retrieval
  → response text generation
  → personalized TTS
  → spoken answer
```

---

## 5. Inventory Of NLP Work Done

The project includes the following concrete NLP and speech-processing work:

- MediaWiki parsing of Wikiquote pages
- quote-template extraction
- quote-section detection
- noisy-section filtering
- page-type classification
- quote validation
- quote normalization
- quote deduplication
- quote/source/author graph modeling
- full-text citation indexing
- lexical query normalization
- keyword extraction
- quote autocomplete
- partial quote completion
- fuzzy quote retrieval
- author retrieval
- fuzzy author matching
- theme-based lexical expansion
- voice-optimized retrieval
- ASR transcription
- ASR domain cleanup and mishearing correction
- speaker embedding creation
- speaker identification by cosine similarity
- rule-based intent classification
- short-memory conversation management
- template-based natural-language response generation
- personalized TTS synthesis

---

## 6. What Is Not Implemented

To keep the report precise, these are notable things the project does **not** fully implement:

- a true semantic embedding index for quote retrieval
- a transformer-based neural intent classifier
- an LLM-based chatbot
- a neural reranker over retrieved quote candidates
- a full semantic RAG pipeline

The system is instead built around:

- strong structured extraction
- graph-based retrieval
- lexical ranking
- speech modules for input and output

---

## 7. Final Assessment

From an NLP perspective, the project is not a single isolated model. It is a **complete applied pipeline** composed of:

- information extraction
- text normalization
- knowledge graph construction
- lexical information retrieval
- speech recognition
- speaker recognition
- dialogue management
- natural-language response realization
- speech synthesis

That makes the project a full end-to-end NLP and speech system rather than only an autocomplete engine or only a voice demo.
