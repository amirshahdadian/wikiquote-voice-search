# The Exhaustive Learning Guide: "Which Quote?"

Welcome to the team! This document is the definitive, comprehensive manual for the "Which Quote?" project. It is designed to take you from a high-level understanding to knowing exactly how every component, script, and API endpoint operates under the hood.

---

## 1. Project Philosophy & Constraints

Our system is a **Monorepo** containing a Python backend and a TypeScript frontend. It is designed under specific constraints:
*   **Local Execution First:** We prioritize running models locally (on Apple Silicon) to ensure privacy and zero API costs.
*   **Modular Service Architecture:** The backend uses dependency injection. The HTTP routers never process data directly; they pass data to Services (`ConversationService`, `VoiceService`), which then interact with Integrations (`Neo4j`, `Whisper`).
*   **Graph over Relational:** Quotes are highly interconnected (Authors, Sources, Pages). A graph database (Neo4j) is exponentially faster for this data shape than a SQL database.

---

## 2. Exhaustive Repository Breakdown

Here is exactly what every directory does:

### The Backend (`/backend/app`)
*   **`/api/routers/`**: Contains the FastAPI endpoints. 
    *   `chat.py` (Text-based conversations)
    *   `voice.py` (Audio-in, audio-out pipeline)
    *   `quotes.py` (Search and autocomplete)
    *   `users.py` (Voice enrollment and TTS preferences)
*   **`/api/schemas/`**: Pydantic models. These ensure that the JSON data going in and out of our APIs is strictly typed and validated.
*   **`/cli/`**: Command Line Interfaces.
    *   `ingest.py`: Parses the XML dump into JSON lines.
    *   `maintenance.py`: Pushes the JSON lines into Neo4j and builds indexes.
    *   `users.py`: CLI for managing enrolled voices.
*   **`/core/`**: System-level configuration. `settings.py` loads the `.env` file. `logging.py` configures the terminal output.
*   **`/integrations/`**: The code that talks to the outside world.
    *   `neo4j_quotes.py`: Cypher queries and graph mapping.
    *   `sqlite_users.py`: Standard SQL for managing user profiles.
    *   `/audio/asr.py`: `mlx-whisper` integration.
    *   `/audio/speaker_id.py`: `resemblyzer` integration.
    *   `/audio/tts.py`: `kokoro-onnx` integration.
*   **`/services/`**: The Business Logic.
    *   `conversation.py`: Routes user intent.
    *   `quote_search.py`: Decides whether to search by Author or by Keyword.
*   **`container.py`**: The Dependency Injector. It wires all the services together so they share the same database connections and AI models in memory.
*   **`main.py`**: The entry point that starts the FastAPI server.

### The Frontend (`/frontend`)
*   **`/app/`**: Next.js App Router. Contains `page.tsx` (the main chat UI) and layout configurations.
*   **`/components/`**: Reusable React UI elements.
    *   `InteractionShell`: The main chat window.
    *   `SpeechButton`: Handles the microphone API and recording states.
*   **`/lib/`**: Helper functions, specifically `api.ts`, which wraps our `fetch` calls to the Python backend.

---

## 3. Deep Dive: Step 1 (The Knowledge Graph)

### The 6-Stage Ingestion Pipeline (`backend/app/cli/ingest.py`)
1.  **XML Parsing:** We use Python's `xml.etree.ElementTree` to stream the 740MB file without crashing the RAM.
2.  **AST Extraction:** `mwparserfromhell` converts the Wikitext into a tree. We search the tree for nodes matching `Template` and filter for names like `quote`, `cquote`, and `quotation`.
3.  **Sanitization:** We recursively strip `<ref>` tags, internal `<!-- comments -->`, and resolve `[[Wikilinks|Display Text]]` to just "Display Text".
4.  **Normalization (`search_normalization.py`):** NFKC Unicode normalization. We strip punctuation from the ends of strings and collapse multiple spaces. 
5.  **Fingerprinting:** We take the normalized quote text and run it through `hashlib.sha256()`. This unique hexadecimal string becomes the Quote's primary key, ensuring deduplication.
6.  **Validation:** We discard quotes under 10 characters or those found in sections labeled "Misattributed."

### The Neo4j Graph Schema (`backend/app/cli/maintenance.py`)
Data is inserted using `MERGE` statements to avoid duplicates.
*   **Nodes:** 
    *   `(:Quote {fingerprint, text, normalized_text})`
    *   `(:Author {name})`
    *   `(:Source {title})`
    *   `(:Page {title, type})`
    *   `(:QuoteOccurrence {key, is_primary})`
*   **Relationships:**
    *   `(Quote)-[:AUTHORED_BY]->(Author)`
    *   `(Quote)-[:APPEARS_IN]->(QuoteOccurrence)`
    *   `(QuoteOccurrence)-[:FOUND_ON]->(Page)`
    *   `(QuoteOccurrence)-[:SOURCED_FROM]->(Source)`

### Lucene Full-Text Search
We create an index on `Quote.normalized_text` and `Author.name`. When a search hits `/api/quotes/search`, we execute:
`CALL db.index.fulltext.queryNodes("quote_index", $query) YIELD node, score`
This allows for typo-tolerant autocomplete.

---

## 4. Deep Dive: Step 2 (Spoken Intelligence)

### A. Automatic Speech Recognition (ASR)
*   **Library:** `mlx-whisper`
*   **Model:** `whisper-large-v3-turbo`. 
*   **Mechanics:** The model converts audio waveforms into Mel-spectrograms, passes them through a Transformer encoder-decoder architecture, and outputs text. By using MLX, the computations are offloaded to the Apple Silicon GPU/NPU, bypassing the CPU bottleneck.

### B. Speaker Identification
*   **Library:** `resemblyzer`
*   **Mechanics:** 
    1.  The audio is sliced into short frames.
    2.  A neural network produces a 256-dimensional vector for each frame.
    3.  These vectors are averaged (L2 normalization) to create a single **d-vector** (Voiceprint).
*   **Verification:** During a voice query, we extract the d-vector. We compute the **Cosine Similarity** (the cosine of the angle between two vectors in 256D space) against enrolled users. 
    *   `Similarity = (A · B) / (||A|| * ||B||)`
    *   If the result is `> 0.75`, we have a positive ID.

### C. Personalized Text-to-Speech (TTS)
*   **Library:** `kokoro-onnx`
*   **Mechanics:** ONNX runtimes execute the Kokoro model. It takes phonemes (text) and a "voice style" embedding, generating a raw audio waveform array. 
*   **Personalization:** The `UserService` looks up the identified user in SQLite. It fetches multipliers for `speaking_rate` and `energy_scale`. We apply these multipliers to the generated numpy array before converting it to WAV bytes via `soundfile`.

---

## 5. The Audio Request Lifecycle (Frontend to Backend)

1.  **React State:** User holds the `SpeechButton`.
2.  **Web Audio API:** The browser's `MediaRecorder` captures raw PCM audio from the mic and encodes it into a `Blob` (usually WebM or MP4 format).
3.  **HTTP POST:** `api.ts` constructs a `FormData` object containing the binary `Blob` and sends it to `/api/voice/query`.
4.  **FastAPI Router:** `voice.py` receives the `UploadFile`. It reads the bytes into RAM.
5.  **Transcription & ID:** The bytes are passed to `VoiceService`. It concurrently runs ASR and Speaker ID.
6.  **Intent Routing:** `ConversationService` analyzes the text. If it matches a regex like `quotes by (.*)`, it triggers a Neo4j author search. Otherwise, it triggers a full-text semantic search.
7.  **Response Generation:** The LLM/Chatbot constructs a text response: *"I found this quote by [Author]: [Quote]"*.
8.  **Synthesis:** The text and identified User ID are passed to `TTSService`. A WAV file is generated in RAM.
9.  **HTTP Response:** FastAPI returns a JSON object containing the `transcript`, `response_text`, and a Base64 encoded audio string (or an audio stream URL).
10. **Frontend Playback:** React updates the chat UI with the text, decodes the Base64 audio into a Blob URL, and plays it via an `HTMLAudioElement`.

---

## 6. Development & Testing Workflow

### Running the Stack Locally
1.  **Database:** Ensure Neo4j is running. (`bolt://127.0.0.1:7687`)
2.  **Backend:** 
    ```bash
    source venv/bin/activate
    uvicorn backend.app.main:app --reload
    ```
3.  **Frontend:** 
    ```bash
    cd frontend
    npm run dev
    ```

### Testing
*   **Backend:** We use `pytest`. You can run the suite via `pytest -q`. Focus on testing the `services/` layer by mocking the Integrations (e.g., mock the Neo4j response to test the Conversation routing logic).
*   **Frontend:** We use standard React testing utilities (`npm run test`).

---

## 7. Day 1 Onboarding Tasks

To get comfortable with the codebase, complete these three tasks:

### Task 1: Add a Custom API Endpoint
1.  Open `backend/app/api/routers/health.py` (or create it).
2.  Add a `GET /api/health/db` endpoint that queries Neo4j `RETURN 1` to verify the database connection is alive.
3.  Check it in `http://localhost:8000/docs`.

### Task 2: Modify the Normalization Logic
1.  Open `backend/app/search_normalization.py`.
2.  Add a regex rule to strip out Wikipedia `[edit]` tags that sometimes slip through the AST parser.
3.  Run the tests to ensure you didn't break existing normalizations.

### Task 3: Adjust the Frontend UI
1.  Open `frontend/components/InteractionShell.tsx`.
2.  Find the rendering logic for the AI's response bubble.
3.  Add a small "Play Audio" button next to every quote returned by the system so users can replay the TTS without asking again.

---

## Conclusion
"Which Quote?" is an exercise in integrating diverse, heavy technologies—Graph Databases, AST Parsing, Signal Processing, and Neural Networks—into a fast, cohesive application. By mastering how data flows from the Wikiquote XML through Neo4j and out to the user's speakers, you will have mastered the core disciplines of modern Data Science and Full-Stack AI Engineering. Welcome aboard!
