# Backend Layout Simplification

## Goal

Make the backend easy to scan and explain by replacing its layered package
hierarchy with a small set of plainly named modules. Preserve behavior; this
is a structural refactor, not a feature rewrite.

## Target structure

```text
backend/
├── __init__.py
├── app.py
├── config.py
├── models.py
├── search.py
├── neo4j.py
├── gemini.py
├── users.py
├── voice.py
├── ingest.py
├── maintenance.py
└── tests/
```

Module responsibilities:

- `app.py`: FastAPI creation, dependencies, routes, and application lifecycle.
- `config.py`: environment settings and application/model logging.
- `models.py`: internal dataclasses and API request/response models.
- `search.py`: lexical/vector retrieval, ranking, query workflow, and conversation.
- `neo4j.py`: graph schema, ingestion writes, and retrieval queries.
- `gemini.py`: intent extraction and document/query embedding operations.
- `users.py`: SQLite persistence and user-profile operations.
- `voice.py`: transcription, speaker recognition, speech generation, and voice flow.
- `ingest.py`: streaming Wikiquote XML extraction and graph loading.
- `maintenance.py`: schema, verification, and resumable embedding-batch commands.

## Compatibility

The refactor must preserve:

- Every existing HTTP path, request body, response body, and status code.
- Existing environment-variable names and defaults.
- Neo4j labels, relationships, indexes, properties, and retrieval behavior.
- SQLite schema, stored users, speaker embeddings, and voice preferences.
- Gemini model configuration and `artifacts/embeddings/current-job.json` format.
- Console commands for ingestion and maintenance.
- Frontend behavior and imports.

The active Gemini batch is external runtime state. It must not be cancelled,
duplicated, committed, or altered by this refactor.

## Migration approach

Move code by responsibility, update internal imports and package entry points,
then delete the empty legacy packages. Combine only closely related modules;
do not introduce compatibility wrappers or re-export packages merely to keep
the old internal import paths alive.

Tests will move to `backend/tests/` unchanged unless an import must be updated.
The JSON extraction fixture may remain because it makes parser tests readable.

## Verification

Completion requires:

- The full backend test suite passes.
- Frontend tests, TypeScript checks, and production build pass.
- FastAPI starts and its route table matches the pre-refactor route table.
- Maintenance verification connects to the live Neo4j database.
- The active Gemini batch checkpoint remains present and valid.
- No API key or runtime artifact is tracked.
- The old backend package directories contain no tracked files.

## Expected result

Production backend modules drop from 32 files in seven nested areas to about
10 plainly named modules in one directory. Tests remain separate so the source
layout is simple without turning the application into an unsafe monolith.
