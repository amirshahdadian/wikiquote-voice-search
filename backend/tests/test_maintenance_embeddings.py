import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from backend.app.cli.maintenance import run_embedding_command
from backend.app.integrations.gemini import GeminiService, prepare_document
from backend.app.integrations.neo4j_repository import Neo4jQuoteRepository


class FakeFiles:
    def __init__(self):
        self.uploaded_lines: list[dict] = []

    def upload(self, *, file, config):
        self.uploaded_lines = [
            json.loads(line)
            for line in Path(file).read_text(encoding="utf-8").splitlines()
        ]
        return SimpleNamespace(name="files/input")

    def download(self, *, file):
        assert file == "files/output"
        return (
            json.dumps(
                {
                    "key": "q1",
                    "response": {"embedding": {"values": [0.0, 1.0]}},
                }
            )
            + "\n"
        ).encode()


class FakeBatches:
    def __init__(self):
        self.created = None

    def create_embeddings(self, **kwargs):
        self.created = kwargs
        return SimpleNamespace(name="batches/123")

    def get(self, *, name):
        assert name == "batches/123"
        return SimpleNamespace(
            name=name,
            state="JOB_STATE_SUCCEEDED",
            dest=SimpleNamespace(file_name="files/output"),
            error=None,
        )


class FakeClient:
    def __init__(self):
        self.files = FakeFiles()
        self.batches = FakeBatches()


class Result:
    def __init__(self, records):
        self.records = records

    def __iter__(self):
        return iter(self.records)


class EmbeddingSession:
    def __init__(self):
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        if "RETURN q.id AS quote_id" in query:
            return Result(
                [
                    {"quote_id": "missing", "quote_text": "Missing vector"},
                    {"quote_id": "old-model", "quote_text": "Old vector"},
                ]
            )
        return Result([])


class EmbeddingDriver:
    def __init__(self):
        self.session_instance = EmbeddingSession()

    @contextmanager
    def session(self):
        yield self.session_instance

    def close(self):
        return None


def test_embedding_batch_uses_document_prefix_and_dimensions():
    client = FakeClient()
    service = GeminiService(
        client, "gemini-3.5-flash-lite", "gemini-embedding-2", 768
    )

    job_name = service.create_embedding_batch(
        [{"quote_id": "q1", "quote_text": "Stay hungry."}]
    )

    assert job_name == "batches/123"
    request = client.files.uploaded_lines[0]
    assert request["key"] == "q1"
    assert request["request"]["content"]["parts"][0]["text"] == prepare_document(
        "Stay hungry."
    )
    assert request["request"]["output_dimensionality"] == 768
    assert client.batches.created["model"] == "gemini-embedding-2"


def test_completed_embedding_batch_maps_keys_to_vectors():
    service = GeminiService(
        FakeClient(), "gemini-3.5-flash-lite", "gemini-embedding-2", 2
    )

    state, records = service.read_embedding_batch("batches/123")

    assert state == "JOB_STATE_SUCCEEDED"
    assert records == {"q1": [0.0, 1.0]}


def test_embedding_backfill_selects_only_missing_or_stale_quotes():
    repository = Neo4jQuoteRepository(driver=EmbeddingDriver())

    rows = repository.pending_embedding_rows("gemini-embedding-2", 768, 100)

    assert [row["quote_id"] for row in rows] == ["missing", "old-model"]
    query, parameters = repository.driver.session_instance.calls[0]
    assert "q.embedding_model <> $model" in query
    assert parameters == {
        "model": "gemini-embedding-2",
        "dimensions": 768,
        "limit": 100,
    }


def test_saved_embedding_records_model_and_dimensions():
    repository = Neo4jQuoteRepository(driver=EmbeddingDriver())

    repository.save_embeddings(
        [{"quote_id": "q1", "embedding": [0.0] * 768}],
        model="gemini-embedding-2",
        dimensions=768,
    )

    query, parameters = repository.driver.session_instance.calls[0]
    assert "q.embedding_model = $model" in query
    assert parameters["model"] == "gemini-embedding-2"
    assert parameters["dimensions"] == 768


class BackfillRepository:
    def __init__(self):
        self.saved = []

    def pending_embedding_rows(self, model, dimensions, limit):
        return [{"quote_id": "q1", "quote_text": "Stay hungry."}]

    def save_embeddings(self, rows, *, model, dimensions):
        self.saved.extend(rows)


class BackfillGemini:
    def __init__(self, state="JOB_STATE_RUNNING"):
        self.state = state

    def create_embedding_batch(self, rows):
        assert rows[0]["quote_id"] == "q1"
        return "batches/123"

    def read_embedding_batch(self, job_name):
        assert job_name == "batches/123"
        records = {"q1": [0.0] * 768} if self.state == "JOB_STATE_SUCCEEDED" else {}
        return self.state, records


def test_embedding_command_submits_once_and_saves_job(tmp_path):
    repository = BackfillRepository()
    gemini = BackfillGemini()

    result = run_embedding_command(
        repository,
        gemini,
        artifacts_dir=tmp_path,
        model="gemini-embedding-2",
        dimensions=768,
    )

    assert result == "JOB_STATE_SUBMITTED"
    saved = json.loads(
        (tmp_path / "embeddings" / "current-job.json").read_text(encoding="utf-8")
    )
    assert saved["job_name"] == "batches/123"


def test_embedding_command_imports_completed_job_and_clears_state(tmp_path):
    job_file = tmp_path / "embeddings" / "current-job.json"
    job_file.parent.mkdir()
    job_file.write_text(
        json.dumps(
            {
                "job_name": "batches/123",
                "model": "gemini-embedding-2",
                "dimensions": 768,
            }
        ),
        encoding="utf-8",
    )
    repository = BackfillRepository()

    result = run_embedding_command(
        repository,
        BackfillGemini("JOB_STATE_SUCCEEDED"),
        artifacts_dir=tmp_path,
        model="gemini-embedding-2",
        dimensions=768,
    )

    assert result == "JOB_STATE_SUCCEEDED"
    assert repository.saved[0]["quote_id"] == "q1"
    assert not job_file.exists()
