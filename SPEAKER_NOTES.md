# Speaker Notes: Which Quote?

These notes match the 9-slide exam deck in `slides.md`. Keep the delivery focused on the two required project stages and the live demo path.

---

### Slide 1: Title
**Say:**
"Good morning. Our project is Which Quote?, a graph-backed Wikiquote search system with multi-user voice interaction. The goal is to take raw Wikiquote data, structure it into a searchable graph, and let users query it by speaking."

---

### Slide 2: What We Built
**Say:**
"The project maps directly to the two required assignment stages. Step 1 builds the quote knowledge graph from the official English Wikiquote dump and exposes autocomplete with attribution. Step 2 adds the spoken interface: ASR, speaker identification, intent routing, and personalized text-to-speech. The key idea is that the voice experience depends on the quality of the underlying quote graph."

---

### Slide 3: Stage 1 - From XML To Quote Records
**Say:**
"The XML dump is only the raw source. We stream pages one by one, parse their Wikitext with mwparserfromhell, extract quote candidates, clean markup and references, classify pages, and deduplicate the output. The result is structured JSON quote records that are ready to be loaded into Neo4j."

---

### Slide 4: Neo4j Graph And Indexing
**Say:**
"Neo4j stores more than the quote text. A Quote node contains the canonical quote, while QuoteOccurrence preserves the specific page-level evidence. That matters because the same quote may appear in several pages with different attribution quality. We then create full-text indexes over quote text, normalized text, author, source, and page fields, searching primary quotes first and the broader corpus as fallback."

---

### Slide 5: Search And Autocomplete
**Say:**
"The main app does not use a black-box search. A rule-based intent parser decides whether the user is asking for a topic, an author, a quote lookup, or a follow-up. Quote search then follows a fallback chain: partial quote matching, primary full-text search, keyword and fuzzy fallback, then secondary corpus search. Autocomplete disables fuzzy matching to keep suggestions precise."

---

### Slide 6: Stage 2 - Voice Interaction
**Say:**
"For the voice path, the browser records audio and sends it to FastAPI. mlx-whisper transcribes the request, resemblyzer identifies the speaker, the conversation service routes the text to Neo4j search, and kokoro-onnx synthesizes the response. The frontend then shows the transcript and quote result and plays the audio answer."

---

### Slide 7: Personalization Layer
**Say:**
"Each user enrolls with at least three samples. Resemblyzer converts those samples into 256-dimensional d-vectors, averages them into a stored voiceprint, and later compares incoming audio with cosine similarity. If the score passes the threshold, we load that user's TTS preferences from SQLite and use them to select the voice, speaking rate, and energy."

---

### Slide 8: Engineering Choices And Validation
**Say:**
"The engineering choices are intentionally practical. Data quality is handled with page classification, validation, deduplication, and primary quote tiers. The speech stack is local-first and Apple Silicon friendly: mlx-whisper, resemblyzer, and kokoro-onnx. Tests focus on the highest-risk parts: parser attribution, normalization, partial quote ranking, API smoke paths, and registration validation. The honest limitation is that search is lexical and heuristic, not semantic RAG."

---

### Slide 9: Demo And Conclusion
**Say:**
"In the demo, we choose or enroll a user, ask a quote fragment or topic query, show the transcript, identify the speaker, retrieve a quote with attribution, and play personalized TTS. The final takeaway is that Which Quote? turns raw Wikiquote XML into a searchable graph and then makes that graph usable through a multi-user voice interface."
