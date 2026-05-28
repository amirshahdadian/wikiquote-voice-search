---
marp: true
theme: default
paginate: true
backgroundColor: #121212
color: #e0e0e0
header: ""
footer: "May 2026 | NLP Final Project | Master's in Data Science"
style: |
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;700&family=JetBrains+Mono:wght@400;700&display=swap');

  section {
    font-family: 'Plus Jakarta Sans', sans-serif;
    padding: 72px 92px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    background: radial-gradient(circle at 0% 0%, #1a1a1a 0%, #121212 100%);
    font-size: 19px;
    overflow: hidden;
  }

  h1, h2, h3 {
    font-family: 'Plus Jakarta Sans', sans-serif;
    margin: 0;
  }

  h1 {
    color: #fff;
    font-weight: 700;
    font-size: 48px;
    letter-spacing: -1.2px;
    text-transform: uppercase;
    margin-bottom: 14px;
  }

  h2 {
    color: #ccff00;
    font-size: 21px;
    font-weight: 400;
    margin-bottom: 34px;
    text-transform: uppercase;
    letter-spacing: 1.4px;
  }

  h3 {
    color: #fff;
    font-size: 18px;
    margin-bottom: 10px;
  }

  p {
    margin: 0;
    line-height: 1.55;
  }

  strong { color: #fff; }

  .accent-box {
    border-left: 3px solid #ccff00;
    padding-left: 26px;
    margin: 28px 0;
  }

  .accent-box h3 {
    font-size: 15px;
    color: #ccff00;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .accent-box p {
    font-size: 18px;
    line-height: 1.55;
    color: #fff;
  }

  .card {
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 22px;
    backdrop-filter: blur(12px);
  }

  .card p, .card li {
    font-size: 16px;
  }

  .split {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 54px;
    align-items: start;
  }

  .split > * {
    min-width: 0;
  }

  .three {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 18px;
  }

  .pipeline {
    display: flex;
    justify-content: space-between;
    align-items: stretch;
    margin-top: 24px;
    gap: 16px;
  }

  .pipeline-step {
    text-align: center;
    flex: 1 1 0;
    padding: 20px 16px;
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
  }

  .pipeline-step .step-num {
    font-family: 'JetBrains Mono', monospace;
    color: #ccff00;
    font-size: 24px;
    font-weight: 700;
    display: block;
    margin-bottom: 10px;
  }

  .pipeline-step h3 {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.58);
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  .pipeline-step p {
    font-size: 13px;
    line-height: 1.35;
    margin: 0;
  }

  ul {
    list-style: none;
    padding: 0;
    margin: 8px 0 0;
  }

  li {
    margin-bottom: 14px;
    padding-left: 24px;
    position: relative;
    line-height: 1.4;
  }

  li::before {
    content: "->";
    position: absolute;
    left: 0;
    color: #ccff00;
    font-family: 'JetBrains Mono', monospace;
    font-weight: bold;
  }

  code {
    font-family: 'JetBrains Mono', monospace;
    background: #1e1e1e;
    color: #ccff00;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 82%;
  }

  .diagram {
    font-family: 'JetBrains Mono', monospace;
    color: #fff;
    background: rgba(0, 0, 0, 0.22);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 22px;
    font-size: 13px;
    line-height: 1.55;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    overflow: hidden;
  }

  .metric {
    font-family: 'JetBrains Mono', monospace;
    color: #ccff00;
    font-size: 34px;
    font-weight: 700;
    display: block;
    margin-bottom: 8px;
  }

  footer {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: rgba(255, 255, 255, 0.2);
  }

  section.title-slide {
    justify-content: center;
  }

  section.title-slide h1 {
    font-size: 72px;
    margin-bottom: 8px;
  }

  section.title-slide h2 {
    color: rgba(255, 255, 255, 0.44);
    font-size: 28px;
    margin-bottom: 46px;
    text-transform: none;
    letter-spacing: 0;
  }

  .team-block {
    display: flex;
    gap: 32px;
    margin-top: 18px;
  }

  .team-member {
    font-size: 14px;
    color: #fff;
    opacity: 0.62;
    font-family: 'JetBrains Mono', monospace;
  }

---

<!-- _class: title-slide -->
<!-- _footer: "" -->

# Which Quote?
## Graph-backed Wikiquote search with multi-user voice interaction

<div class="team-block">
  <div class="team-member">Amir Hossein Shahdadian</div>
  <div class="team-member">Mahtab Taheri</div>
  <div class="team-member">Yasaman Zahedan</div>
</div>

---

## What We Built
### A complete two-stage NLP system, aligned with the exam requirements.

<div class="split">
  <div class="card">
    <h3>Step 1 - Quote Knowledge Graph</h3>
    <ul>
      <li>Start from the official English Wikiquote XML dump.</li>
      <li>Parse noisy Wikitext into clean quote records.</li>
      <li>Store quote text, author, source, page, and occurrence context in Neo4j.</li>
      <li>Expose autocomplete and attributable quote retrieval.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Step 2 - Voice Interface</h3>
    <ul>
      <li>Record spoken questions in the browser.</li>
      <li>Transcribe speech with <code>mlx-whisper</code>.</li>
      <li>Identify enrolled speakers with voice embeddings.</li>
      <li>Answer with personalized <code>kokoro-onnx</code> TTS.</li>
    </ul>
  </div>
</div>

<div class="accent-box">
  <h3>Core Idea</h3>
  <p>Reliable voice search depends on a reliable quote graph: the system must know the quote, the author, the source, and where that evidence came from.</p>
</div>

---

## Stage 1: From XML To Quote Records
### The raw dump is transformed before the app ever searches it.

<div class="pipeline">
  <div class="pipeline-step">
    <span class="step-num">01</span>
    <h3>XML Stream</h3>
    <p>Read Wikiquote pages without loading the full dump into memory.</p>
  </div>
  <div class="pipeline-step">
    <span class="step-num">02</span>
    <h3>Wikitext AST</h3>
    <p><code>mwparserfromhell</code> parses templates, links, refs, and nested markup.</p>
  </div>
  <div class="pipeline-step">
    <span class="step-num">03</span>
    <h3>Extraction</h3>
    <p>Collect quote text, author, source, section context, and page type.</p>
  </div>
  <div class="pipeline-step">
    <span class="step-num">04</span>
    <h3>Quality Gates</h3>
    <p>Normalize text, remove artifacts, filter noise, and deduplicate.</p>
  </div>
  <div class="pipeline-step">
    <span class="step-num">05</span>
    <h3>JSON Output</h3>
    <p>Write structured records consumed by the Neo4j loader.</p>
  </div>
</div>

<div class="accent-box">
  <h3>Why AST Parsing Matters</h3>
  <p>Wiki markup is nested and inconsistent; an Abstract Syntax Tree lets us inspect template and link structure instead of relying on fragile regular expressions.</p>
</div>

---

## Neo4j Graph And Indexing
### We store provenance, not only text.

<div class="split">
  <div class="card">
    <h3>Graph Relationships</h3>
    <p><code>Author -> Quote</code></p>
    <p><code>Quote -> QuoteOccurrence</code></p>
    <p><code>QuoteOccurrence -> Source</code></p>
    <p><code>QuoteOccurrence -> Page</code></p>
    <br>
    <p><strong>Quote</strong> stores canonical text. <strong>Occurrence</strong> stores evidence.</p>
  </div>
  <div class="card">
    <h3>Why QuoteOccurrence Exists</h3>
    <ul>
      <li>The same quote can appear on multiple Wikiquote pages.</li>
      <li>Each occurrence may have different citation strength or context.</li>
      <li>We deduplicate the quote while preserving evidence.</li>
      <li>Primary/secondary tiers rank cleaner occurrences first.</li>
    </ul>
  </div>
</div>

<div class="accent-box">
  <h3>Search Indexes</h3>
  <p>Neo4j full-text indexes cover quote text, normalized text, author, source, and page fields. The app searches <code>PrimaryQuote</code> first, then falls back to the broader quote corpus.</p>
</div>

---

## Search And Autocomplete
### The main app uses a controlled fallback chain, not a black box.

<div class="split">
  <div>
    <h3>Intent Routing</h3>
    <ul>
      <li><code>quotes about courage</code> becomes a topic search.</li>
      <li><code>quotes by Einstein</code> becomes an author search.</li>
      <li><code>who said i have a dream</code> becomes quote lookup.</li>
      <li><code>read it again</code> and <code>another one</code> use conversation memory.</li>
    </ul>
  </div>
  <div>
    <h3>Quote Search Order</h3>
    <div class="accent-box">
      <p>partial quote match</p>
      <p>primary full-text search</p>
      <p>primary keyword / fuzzy fallback</p>
      <p>secondary full-text + fallback</p>
    </div>
  </div>
</div>

<div class="accent-box">
  <h3>Important Detail</h3>
  <p>Autocomplete disables fuzzy matching for precision. Main chat and voice search enable lightweight lexical fuzzy matching, based on word overlap rather than vector embeddings.</p>
</div>

---

## Stage 2: Voice Interaction
### Spoken input becomes a graph query, then an audible answer.

<div class="pipeline">
  <div class="pipeline-step">
    <span class="step-num">01</span>
    <h3>Capture</h3>
    <p>Browser <code>MediaRecorder</code> captures user audio.</p>
  </div>
  <div class="pipeline-step">
    <span class="step-num">02</span>
    <h3>ASR</h3>
    <p><code>mlx-whisper</code> transcribes and normalizes the request.</p>
  </div>
  <div class="pipeline-step">
    <span class="step-num">03</span>
    <h3>Speaker ID</h3>
    <p><code>resemblyzer</code> compares the voice to enrolled embeddings.</p>
  </div>
  <div class="pipeline-step">
    <span class="step-num">04</span>
    <h3>Retrieve</h3>
    <p>The intent parser routes the text to Neo4j search.</p>
  </div>
  <div class="pipeline-step">
    <span class="step-num">05</span>
    <h3>Synthesize</h3>
    <p><code>kokoro-onnx</code> generates the personalized response audio.</p>
  </div>
</div>

<div class="accent-box">
  <h3>Runtime Stack</h3>
  <p>FastAPI orchestrates the services; Next.js provides the recording, chat, user management, and audio playback interface.</p>
</div>

---

## Personalization Layer
### The recognized speaker controls how the answer is spoken.

<div class="split">
  <div class="card">
    <h3>Enrollment</h3>
    <ul>
      <li>Each user provides at least three voice samples.</li>
      <li><code>resemblyzer</code> extracts 256-dimensional d-vectors.</li>
      <li>Samples are averaged into one stored voiceprint.</li>
      <li>User profile and TTS settings are stored in SQLite.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Recognition + TTS</h3>
    <ul>
      <li>Incoming audio is embedded with the same model.</li>
      <li>Cosine similarity selects the best enrolled speaker.</li>
      <li>Threshold <code>0.75</code> avoids weak matches.</li>
      <li>The user profile selects Kokoro voice, rate, and energy.</li>
    </ul>
  </div>
</div>

<div class="accent-box">
  <h3>Fallback</h3>
  <p>If Kokoro synthesis fails, the app can fall back to <code>gTTS</code>, which uses Google's network TTS endpoint. The primary path remains local-first.</p>
</div>

---

## Engineering Choices And Validation
### We optimized for explainability, local execution, and demo reliability.

<div class="three">
  <div class="card">
    <span class="metric">01</span>
    <h3>Data Quality</h3>
    <p>Page classification, quote validation, deduplication, and primary quote tiers reduce noisy Wikiquote extraction.</p>
  </div>
  <div class="card">
    <span class="metric">02</span>
    <h3>Local Models</h3>
    <p><code>mlx-whisper</code>, <code>resemblyzer</code>, and <code>kokoro-onnx</code> avoid CUDA dependency and fit Apple Silicon development.</p>
  </div>
  <div class="card">
    <span class="metric">03</span>
    <h3>Focused Tests</h3>
    <p>Tests cover API smoke paths, parser attribution, text normalization, partial quote ranking, and user registration rules.</p>
  </div>
</div>

<div class="accent-box">
  <h3>Honest Limitation</h3>
  <p>Search is lexical and heuristic, not semantic RAG. This makes behavior deterministic and defensible, but paraphrased queries are a future improvement area.</p>
</div>

---

<!-- _class: title-slide -->
<!-- footer: "Thank you for your attention. Any questions?" -->

# Demo & Conclusion
## Validating the complete pipeline in real time.

<div class="accent-box">
  <h3>Live Demo Path</h3>
  <p>Choose or enroll a user -> ask a quote fragment or topic query -> show transcript -> identify speaker -> retrieve quote with attribution -> play personalized TTS.</p>
</div>

<div class="accent-box">
  <h3>Final Claim</h3>
  <p><strong>Which Quote?</strong> turns raw Wikiquote XML into a searchable graph, then makes that graph usable through multi-user voice interaction.</p>
</div>
