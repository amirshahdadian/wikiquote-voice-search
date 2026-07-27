# Backend Layout Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the layered backend package tree with about ten plainly named modules while preserving every external behavior.

**Architecture:** Consolidate files by real responsibility at the `backend/` package root. Update imports and entry points directly, then delete the legacy package tree rather than retaining compatibility wrappers.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Neo4j, SQLite, Google Gen AI, pytest

## Global Constraints

- Preserve every HTTP path, payload, response, and status code.
- Preserve environment variables, Neo4j schema, SQLite data, Gemini checkpoint format, and CLI behavior.
- Do not change, cancel, duplicate, or commit the active Gemini batch state.
- Do not add dependencies or compatibility wrapper packages.
- Keep the frontend unchanged.

---

### Task 1: Capture compatibility baselines

**Files:**
- Modify: `backend/tests/test_app_smoke.py`
- Modify: `backend/tests/test_neo4j_schema.py`

**Interfaces:**
- Consumes: current `create_app()` and maintenance parser.
- Produces: regression checks for route paths and CLI command names.

- [ ] **Step 1: Add explicit baseline assertions**

Assert that the application exposes the current route/method pairs and that
maintenance still accepts `schema`, `embed`, and `verify`.

- [ ] **Step 2: Run baseline tests**

Run:

```bash
pytest -q backend/tests/test_app_smoke.py backend/tests/test_neo4j_schema.py
```

Expected: PASS before file moves.

- [ ] **Step 3: Commit the baseline**

```bash
git add backend/tests/test_app_smoke.py backend/tests/test_neo4j_schema.py
git commit -m "test: lock backend public interfaces"
```

### Task 2: Flatten models, configuration, and persistence

**Files:**
- Create: `backend/config.py`
- Create: `backend/models.py`
- Create: `backend/neo4j.py`
- Create: `backend/gemini.py`
- Create: `backend/users.py`
- Modify: `backend/tests/test_settings.py`
- Modify: `backend/tests/test_gemini_integration.py`
- Modify: `backend/tests/test_neo4j_schema.py`
- Modify: `backend/tests/test_users_storage.py`

**Interfaces:**
- Produces: `Settings`, `settings`, logging helpers, domain/API models,
  `Neo4jQuoteRepository`, `GeminiService`, SQLite helpers, and `UserService`
  from plainly named root modules.

- [ ] **Step 1: Move related implementations into the five root modules**

Combine each old module group without changing public class/function
signatures. Replace internal imports with `backend.<module>` imports.

- [ ] **Step 2: Update focused test imports**

Import the same names from their new root modules.

- [ ] **Step 3: Run focused tests**

```bash
pytest -q backend/tests/test_settings.py \
  backend/tests/test_gemini_integration.py \
  backend/tests/test_neo4j_schema.py \
  backend/tests/test_users_storage.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend backend/tests
git commit -m "refactor: flatten backend data modules"
```

### Task 3: Flatten search, voice, application, and commands

**Files:**
- Create: `backend/search.py`
- Create: `backend/voice.py`
- Create: `backend/app.py`
- Create: `backend/ingest.py`
- Create: `backend/maintenance.py`
- Modify: `pyproject.toml`
- Modify: all `backend/tests/test_*.py` imports

**Interfaces:**
- Produces: `create_app`, `app`, search/conversation workflow, voice/user
  flows, and the unchanged ingestion and maintenance console commands.

- [ ] **Step 1: Consolidate search and voice code**

Move search/ranking/conversation into `search.py`; move ASR, speaker
identification, TTS, and voice orchestration into `voice.py`.

- [ ] **Step 2: Consolidate FastAPI application code**

Move dependencies, schemas, routes, container, and lifecycle into `app.py`.
Keep route decorators, paths, methods, dependency behavior, and status codes
unchanged.

- [ ] **Step 3: Move CLI modules and update entry points**

Move ingestion and maintenance to their root files. Update `pyproject.toml`
entry points to `backend.ingest:main` and `backend.maintenance:main`.

- [ ] **Step 4: Update remaining tests and run the suite**

```bash
pytest -q
```

Expected: all backend tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend pyproject.toml
git commit -m "refactor: flatten backend runtime modules"
```

### Task 4: Delete legacy packages, document, verify, and publish

**Files:**
- Delete: `backend/app/`
- Modify: `README.md`
- Modify: `REPORT.md`

**Interfaces:**
- Consumes: all new root modules.
- Produces: the final ten-module backend with no legacy package wrappers.

- [ ] **Step 1: Delete the legacy tree and scan imports**

Confirm no tracked code references `backend.app`, and no old package files
remain.

- [ ] **Step 2: Update documentation**

Replace old paths and architecture descriptions with the new backend tree and
commands.

- [ ] **Step 3: Run complete verification**

```bash
pytest -q
cd frontend && npm test -- --run && npm run typecheck && npm run build
python -m backend.maintenance verify
```

Expected: all tests/builds pass and live Neo4j counts print successfully.

- [ ] **Step 4: Verify runtime safety**

Confirm `artifacts/embeddings/current-job.json` remains valid and ignored,
`.env` remains ignored, and no key-like value is tracked.

- [ ] **Step 5: Commit and push**

```bash
git add backend README.md REPORT.md pyproject.toml
git commit -m "refactor: simplify backend layout"
git push origin main
```
