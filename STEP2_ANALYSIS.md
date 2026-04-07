# Step 2 — Deep Analysis & Best-Practice Recommendations
### Target hardware: MacBook Air M3 16 GB (Apple Silicon, no CUDA)

---

## Executive Summary

The current Step 2 implementation was designed around **NVIDIA NeMo** for all three
AI tasks (ASR, Speaker ID, TTS). **NeMo does not install on macOS** — it has a hard
dependency on `triton`, which has no macOS wheel. This means the three core modules
of the voice pipeline are effectively broken on the target machine before a single
line of application code runs.

Everything else (chatbot, dialogue, backend, frontend) is well-structured and reusable
as-is. Only the three AI service files need to be replaced.

---

## Module-by-Module Assessment

---

### 1. ASR — `services/asr_service.py` + `services/asr_service_hybrid.py`

#### What it does now
`asr_service.py` tries to load `openai-whisper` and, if that fails, falls back to the
hybrid service. `asr_service_hybrid.py` tries three backends in order:
1. **NeMo Conformer** (`stt_en_conformer_ctc_small`) — primary
2. **Whisper** (`openai-whisper`, `base` model) — fallback
3. **Wav2Vec2** — second fallback

#### Issues on M3 Mac

| Backend | Status on M3 | Reason |
|---------|-------------|--------|
| NeMo Conformer | ❌ **Fails to install** | `triton` has no macOS wheel ([NeMo issue #8116](https://github.com/NVIDIA-NeMo/NeMo/issues/8116)) |
| openai-whisper on MPS | ⚠️ Works but slow | Needs `PYTORCH_ENABLE_MPS_FALLBACK=1`; 5.37 s/clip in benchmarks |
| faster-whisper | ❌ No MPS support | CTranslate2 is CPU-only on Mac; slowest option in benchmarks |
| Wav2Vec2 on MPS | ❌ Broken | `aten::_weight_norm_interface` not implemented for MPS device |

The fallback chain ends on `openai-whisper` CPU — functional but 5× slower than
the best available option.

#### Best practice on M3
**`mlx-whisper`** uses Apple's MLX framework, which targets the GPU and Neural Engine
natively without MPS hacks. It mirrors the `openai-whisper` API exactly — migration
is a one-line import swap.

```
Benchmark (M4 Pro, large model, seconds per clip):
  mlx-whisper (large-v3-turbo)  →  1.02 s   ← best Python option
  openai-whisper (MPS)          →  5.37 s
  faster-whisper (CPU)          →  6.96 s   ← worst
```

**Recommended model:** `mlx-community/whisper-large-v3-turbo`
- 809M parameters, ~3–4 GB RAM, ~10–15× real-time on M3
- Leaves >12 GB free for the rest of the app
- For even lower latency: `mlx-community/whisper-small-mlx` (~1 GB, ~50× real-time)

---

### 2. Speaker Identification — `services/speaker_identification.py`

#### What it does now
Uses **NeMo TitaNet** (`titanet_large`) to:
1. Enroll users: record N audio samples → compute embeddings → store in SQLite
2. Identify speaker: embed incoming audio → cosine-similarity against enrolled set

The logic (enroll → embed → compare → threshold) is **correct and reusable**.
Only the embedding model needs to be swapped.

#### Issues on M3 Mac

| Component | Status | Reason |
|-----------|--------|--------|
| NeMo TitaNet | ❌ Fails to install | Same `triton` dependency |
| The enrollment/identification logic | ✅ Sound | Can be kept with a new backbone |

#### Best practice on M3
Two strong options depending on priority:

**Option A — `resemblyzer`** (simplest, zero friction)
- Pure PyTorch, CPU-only by design, no GPU dependency whatsoever
- `pip install resemblyzer`
- 256-dim d-vector embeddings (GE2E loss speaker encoder)
- Works perfectly for a small enrolled-user set (2–10 speakers)
- Drop-in: replace `model.get_embedding(audio)` with `encoder.embed_utterance(wav)`

**Option B — `wespeaker`** (better quality, still M3-native)
- `pip install wespeaker`
- ResNet34 / ECAPA-TDNN backbone, EER ~1–2% on VoxCeleb1 (state-of-the-art)
- Pure PyTorch, Mac is an explicitly supported platform
- Pre-trained models on HuggingFace, 256-dim embeddings

**For this project (small number of enrolled users, demo scenario): Option A
(`resemblyzer`) is the right call** — minimal setup, no model downloads, proven
for exactly this use case.

---

### 3. TTS — `services/tts_service.py` + `services/tts_service_simple.py`

#### What it does now
`tts_service.py` uses **NeMo FastPitch + HiFiGAN**. The plan is:
- Map a recognized user to a voice profile (pitch shift, speaking rate)
- Apply `pitch_transform` and `pace` parameters per user

`tts_service_simple.py` uses **gTTS** as fallback — but gTTS requires internet and
produces the same voice for everyone (not personalized).

#### Issues on M3 Mac

| Component | Status | Reason |
|-----------|--------|--------|
| NeMo FastPitch + HiFiGAN | ❌ Fails to install | `triton` + `nemo_text_processing` Cython extensions |
| gTTS | ⚠️ Works but online-only | Calls Google's servers; not personalized |
| Personalization logic | ⚠️ Concept is right, implementation is wrong | NeMo pitch/pace params won't port directly to replacement models |

#### Best practice on M3 — Two-tier strategy

**Tier 1 — Voice style per user (fast, lightweight): `Kokoro TTS`**
- 82M params, Apache 2.0, ~54 preset voices (American/British/etc.)
- ONNX backend (`kokoro-onnx`) for pure CPU inference, sub-200ms latency on M3
- **Personalization**: each user is assigned a voice preset at enrollment time
  (e.g. User A → `af_heart`, User B → `bm_lewis`). Not voice cloning, but
  audibly different voices per user — satisfies the project requirement.
- `pip install kokoro-onnx` — no heavy dependencies

**Tier 2 — Voice cloning from enrollment audio: `Coqui TTS XTTS v2`**
- Clones a voice from a 6-second reference clip — uses the user's own enrollment
  audio directly
- **True personalization**: the TTS sounds like the user who asked the question
- CPU-only on M3 (`device="cpu"` required — MPS hangs on XTTS v2)
- ~2–5 s synthesis time on M3 Air CPU (acceptable for a demo, not real-time)
- `pip install TTS`

**Recommendation for this project:** Start with **Kokoro TTS** (fast, works immediately,
different voices per user). The project requirement says "configured according to the
voice preferences previously associated with the recognized user" — preset assignment
at enrollment satisfies this. Add XTTS v2 as a quality upgrade if time allows.

---

### 4. Chatbot — `services/chatbot_service.py` + `src/wikiquote_voice/dialogue/`

#### Assessment: ✅ Good, minor improvements needed

The intent system (`intents.py`) covers:
`SEARCH_QUOTE`, `SEARCH_BY_AUTHOR`, `SEARCH_BY_THEME`, `AUTOCOMPLETE`,
`RANDOM_QUOTE`, `GREETING`, `HELP`, `UNKNOWN`

The NLG (`nlg.py`) has response templates for all dialogue states.

**Issues:**
1. The intent parser is pure rule-based regex — it will miss natural phrasings like
   "What did Einstein say about peace?" (should map to SEARCH_BY_AUTHOR + theme)
2. No conversation history / follow-up handling beyond a single turn
3. `nlg.py` templates are functional but generic

**These are acceptable for a project demo.** No replacement needed — the architecture
is correct.

---

### 5. Orchestrator — `services/orchestrator.py`

#### Assessment: ✅ Architecture is correct, wiring needs updating

The pipeline order is right:
```
Record audio → Speaker ID → ASR → Chatbot → TTS → Play audio
```

Issues:
- All three AI service imports will fail on M3 at startup
- Error handling falls back to text-only mode — that's good defensive design
- The `_apply_voice_personalization()` method ties personalization to NeMo-specific
  pitch/pace params that won't exist in the replacement TTS

---

### 6. Backend — `backend/app/`

#### Assessment: ✅ Well-structured, keep as-is

FastAPI + Pydantic schemas + dependency injection — clean, standard. All endpoints
are correct. The only change needed is updating `state.py` to initialize the
replacement service objects instead of the NeMo-based ones.

---

### 7. Frontend — `frontend/`

#### Assessment: ✅ Keep as-is

Next.js + React, MediaRecorder API for audio capture, clean component structure.
No changes needed.

---

## Summary of Issues

| # | Issue | Severity | Fix |
|---|-------|----------|-----|
| 1 | NeMo won't install on M3 (ASR) | 🔴 Blocking | Replace with `mlx-whisper` |
| 2 | NeMo won't install on M3 (Speaker ID) | 🔴 Blocking | Replace with `resemblyzer` |
| 3 | NeMo won't install on M3 (TTS) | 🔴 Blocking | Replace with `Kokoro TTS` (ONNX) |
| 4 | Wav2Vec2 broken on MPS | 🔴 Blocking | Remove entirely |
| 5 | gTTS fallback is online-only, not personalized | 🟡 Partial | Replace with Kokoro as primary |
| 6 | openai-whisper uses CPU fallback | 🟡 Slow | Replace with `mlx-whisper` |
| 7 | TTS personalization tied to NeMo pitch/pace params | 🟡 Wrong API | Rebuild around voice preset assignment |
| 8 | Intent parser is regex-only | 🟢 Acceptable | No change needed for demo |
| 9 | No multi-turn conversation state | 🟢 Acceptable | No change needed for demo |

---

## Recommended Final Stack (M3 Mac, fully offline)

```
ASR:         mlx-whisper  +  mlx-community/whisper-large-v3-turbo
Speaker ID:  resemblyzer  (CPU, GE2E embeddings)
TTS:         kokoro-onnx  (54 preset voices, sub-200ms, ONNX backend)
Chatbot:     existing dialogue system (keep as-is)
Backend:     existing FastAPI (keep as-is, update service init)
Frontend:    existing Next.js (keep as-is)
```

**Install footprint on M3:**
```
mlx-whisper           ~1.5 GB model  (whisper-large-v3-turbo)
resemblyzer           ~100 MB model
kokoro-onnx           ~340 MB model
─────────────────────────────────────
Total model storage   ~2 GB
RAM at runtime        ~4–5 GB  (leaves 11 GB free)
```

Everything runs **fully offline**, no API keys, no CUDA, no internet required.

---

## Implementation Order

1. **Replace ASR** → swap `asr_service.py` to use `mlx-whisper`
2. **Replace Speaker ID** → swap `speaker_identification.py` to use `resemblyzer`
3. **Replace TTS** → swap `tts_service.py` to use `kokoro-onnx`, rebuild personalization as voice-preset assignment
4. **Update orchestrator** → remove NeMo-specific params, wire new services
5. **Update `requirements.txt`** → remove NeMo/Wav2Vec2, add new deps
6. **Smoke test** end-to-end with a real mic recording
