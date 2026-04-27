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

Representative parser code:

```python
# backend/app/cli/ingest.py
@dataclass
class ExtractedQuote:
    quote: str
    author: str
    page_title: str
    page_type: str
    source: Optional[str] = None
    normalized_quote: Optional[str] = None
    quote_fingerprint: Optional[str] = None
    occurrence_key: Optional[str] = None

def _canonicalize_text(self, text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
    normalized = normalized.lower()
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'^[\'"“”‘’«»\-\s]+|[\'"“”‘’«»\-\s]+$', '', normalized)
    return normalized.strip()
```

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

Representative Neo4j loading code:

```cypher
// backend/app/cli/maintenance.py
MERGE (quote:Quote {fingerprint: quote_data.quote_fingerprint})
  ON CREATE SET
    quote.text = quote_data.quote,
    quote.canonical_text = coalesce(quote_data.canonical_quote, quote_data.quote),
    quote.normalized_text = coalesce(quote_data.normalized_quote, quote_data.canonical_quote, quote_data.quote),
    quote.primary_author = author_name,
    quote.primary_source = source_title,
    quote.primary_page = quote_data.page_title

MERGE (occurrence:QuoteOccurrence {key: quote_data.occurrence_key})
  ON CREATE SET
    occurrence.author_name = author_name,
    occurrence.source_title = source_title,
    occurrence.page_title = quote_data.page_title,
    occurrence.quote_type = quote_data.quote_type,
    occurrence.is_primary = occurrence_is_primary
```

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

Representative search logic:

```python
# backend/app/integrations/neo4j_quotes.py
def search_quotes(self, query: str, limit: int = 10, include_fuzzy: bool = True) -> List[Dict[str, Any]]:
    if not query or not query.strip():
        return []

    query = " ".join(query.strip().split())
    theme_match = re.match(r"^quotes?\s+(?:about|on|regarding)\s+(.+)$", query, re.IGNORECASE)
    if theme_match:
        return self.search_by_theme(theme_match.group(1).strip(), limit=limit)

    if self._looks_like_partial_quote(query):
        return self._partial_quote_search(query, limit)

    results = self._run_search_pipeline(query, limit, include_fuzzy=include_fuzzy)
    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return results[:limit]
```

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

Representative ASR code:

```python
# backend/app/integrations/audio/asr.py
def transcribe(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
    decode_opts = {
        "fp16": True,
        "temperature": 0.0,
        "initial_prompt": _INITIAL_PROMPT,
    }
    if language:
        decode_opts["language"] = language

    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=self.model_name,
        verbose=False,
        **decode_opts,
    )
    text = result["text"].strip()
    return {"text": text, "normalized_text": self.normalize_command(text)}
```

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

Representative speaker-identification code:

```python
# backend/app/integrations/audio/speaker_id.py
def identify_speaker(self, audio_path: str, enrolled_users: Dict[str, np.ndarray]) -> Tuple[Optional[str], float]:
    if not enrolled_users:
        return None, 0.0

    query = self.extract_embedding(audio_path)
    best_id, best_score = None, 0.0

    for uid, enrolled_emb in enrolled_users.items():
        score = self.compute_similarity(query, enrolled_emb)
        if score > best_score:
            best_score = score
            best_id = uid

    if best_score >= self.threshold:
        return best_id, best_score
    return None, best_score
```

## 5.3 Conversational Layer

The conversational module is implemented in:

- `backend/app/services/conversation.py`

This layer is responsible for:

- intent detection
- follow-up management
- routing user input to the quote-search service
- formatting the response text used by the frontend and TTS modules

The approach is rule-based and deterministic, which is appropriate for the narrow task domain of quote lookup and follow-up handling.

Representative orchestration code:

```python
# backend/app/services/conversation.py
def process_voice_query(self, audio_bytes: bytes, filename: str, conversation_id: str | None = None,
                        selected_user_id: str | None = None) -> dict[str, Any]:
    conversation = self._get_or_create_conversation(conversation_id)
    transcript, normalized_transcript = self.voice_service.transcribe_bytes(audio_bytes, filename)

    if selected_user_id:
        recognized_user = self.user_service.load_recognized_user(selected_user_id, 1.0, "selected")
    else:
        matched_user, confidence = self.voice_service.identify_speaker(audio_bytes, filename)
        recognized_user = self.user_service.load_recognized_user(matched_user, confidence, "speaker_id") if matched_user else None

    response = self._build_query_response(transcript, conversation, selected_user_id, recognized_user, [])
    response.update({"conversation_id": conversation.conversation_id, "transcript": transcript})
    return response
```

## 5.4 Personalized Text-to-Speech

The TTS modules are implemented in:

- `backend/app/integrations/audio/tts.py`
- `backend/app/integrations/audio/tts_fallback.py`

The main TTS engine is `kokoro-onnx`. A per-user voice profile is associated with each registered speaker, allowing different users to hear different synthesized voices. This satisfies the Step 2 requirement that responses should be personalized according to the recognized user's associated voice preferences.

If the primary TTS path is unavailable, the system exposes a fallback TTS path.

Representative personalization code:

```python
# backend/app/integrations/audio/tts.py
def synthesize_personalized(self, text: str, user_id: str = None, output_path: str = None,
                            preferences: Dict[str, Any] = None) -> np.ndarray:
    if preferences is None:
        preferences = self.get_user_preferences(user_id) if user_id else self._default_preferences()

    voice = str(preferences.get("style") or DEFAULT_VOICE)
    speed = float(preferences.get("speaking_rate") or DEFAULT_SPEED)
    energy = float(preferences.get("energy_scale") or 1.0)

    if voice not in KOKORO_VOICES and not voice.startswith(("af_", "am_", "bf_", "bm_")):
        voice = DEFAULT_VOICE

    audio, sr = self._synth(text, voice=voice, speed=speed)
    audio = np.clip(audio * energy, -1.0, 1.0)
    if output_path:
        sf.write(output_path, audio, sr)
    return audio
```

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

Representative backend wiring:

```python
# backend/app/container.py
speaker_service = SpeakerIdentificationService(threshold=0.75)
self.quote_search = QuoteSearchService(app_settings)
self.voice = VoiceService(app_settings, speaker_service=speaker_service)
self.users = UserService(app_settings, speaker_service=speaker_service)
self.conversation = ConversationService(
    self.quote_search,
    self.users,
    self.voice,
    app_settings.conversation_history_limit,
)

# backend/app/main.py
app.include_router(health_router)
app.include_router(quotes_router)
app.include_router(authors_router)
app.include_router(users_router)
app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(audio_router)
```

---

## 7. Frontend

The frontend is implemented with `Next.js` and provides:

- the main conversational interface
- advanced quote-search views
- user registration and management screens
- voice interaction and response playback

Representative frontend integration code:

```typescript
// frontend/lib/api.ts
export async function submitVoiceQuery(payload: {
  audio: Blob;
  filename?: string;
  conversation_id?: string | null;
  selected_user_id?: string | null;
}): Promise<VoiceQueryResponse> {
  const formData = new FormData();
  formData.append("audio", payload.audio, payload.filename ?? "recording.webm");
  if (payload.conversation_id) formData.append("conversation_id", payload.conversation_id);
  if (payload.selected_user_id) formData.append("selected_user_id", payload.selected_user_id);
  return requestJson<VoiceQueryResponse>("/api/voice/query", { method: "POST", body: formData });
}

// frontend/components/interaction-shell.tsx
async function sendVoiceQuery(sample: LocalAudioSample) {
  const payload = await submitVoiceQuery({
    audio: sample.blob,
    filename: sample.name,
    conversation_id: conversationId,
    selected_user_id: selectedUserId,
  });
  updateConversation((payload as VoiceQueryResponse).transcript, payload as VoiceQueryResponse);
}
```

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

Representative SQLite schema:

```sql
-- backend/app/integrations/sqlite_users.py
CREATE TABLE IF NOT EXISTS user_tts_preferences (
    user_id TEXT PRIMARY KEY,
    pitch_scale REAL DEFAULT 1.0,
    speaking_rate REAL DEFAULT 1.0,
    energy_scale REAL DEFAULT 1.0,
    style TEXT DEFAULT 'neutral',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    group_identifier TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

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
