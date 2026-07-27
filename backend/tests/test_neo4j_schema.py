from contextlib import contextmanager

import pytest

from backend.maintenance import build_parser
from backend.neo4j import Neo4jQuoteRepository
from backend.neo4j import SCHEMA_STATEMENTS, ensure_schema


class RecordingSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, parameters=None, **kwargs):
        self.calls.append((query, {**(parameters or {}), **kwargs}))
        return []


class RecordingDriver:
    def __init__(self):
        self.session_instance = RecordingSession()

    @contextmanager
    def session(self):
        yield self.session_instance

    def close(self):
        return None


class CountResult:
    def __init__(self, count):
        self.count = count

    def single(self):
        return {"count": self.count}


class IndexResult:
    def __init__(self, online):
        self.online = online

    def single(self):
        return {"online": self.online}


class CountSession:
    def __init__(self):
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        return CountResult(2 if "embedding_model" in query else 0)


class CountDriver:
    def __init__(self):
        self.session_instance = CountSession()

    @contextmanager
    def session(self):
        yield self.session_instance

    def close(self):
        pass


class IndexDriver:
    def __init__(self, online):
        self.online = online
        self.connected = False

    def verify_connectivity(self):
        self.connected = True

    @contextmanager
    def session(self):
        yield self

    def run(self, query, **parameters):
        self.query = query
        self.parameters = parameters
        return IndexResult(self.online)


def test_schema_has_only_explainable_constraints_and_indexes():
    joined = "\n".join(SCHEMA_STATEMENTS)

    assert "quote_id_unique" in joined
    assert "attribution_id_unique" in joined
    assert "author_key_unique" in joined
    assert "work_key_unique" not in joined
    assert "wikiquote_page_id_unique" not in joined
    assert "quote_embedding" in joined
    assert "quote_search_text" in joined
    assert "q.normalized_text" not in joined
    assert "`vector.dimensions`: 768" in joined
    assert "`vector.similarity_function`: 'cosine'" in joined


def test_ensure_schema_executes_every_statement_once():
    session = RecordingSession()

    ensure_schema(session)

    assert [query for query, _ in session.calls] == SCHEMA_STATEMENTS


def test_loader_stores_display_provenance_on_attribution():
    driver = RecordingDriver()
    repository = Neo4jQuoteRepository(driver=driver)
    row = {
        "quote_id": "quote-1",
        "attribution_id": "attribution-1",
        "quote": "A sufficiently long quotation.",
        "normalized_quote": "a sufficiently long quotation",
        "author": "Test Author",
        "work": "Test Work",
        "page_id": 42,
        "revision_id": 84,
        "page_title": "Test Author",
        "page_type": "person",
        "quote_type": "sourced",
        "citation": "Test Work, p. 1",
    }

    repository.load([row], batch_size=100)

    query, parameters = driver.session_instance.calls[0]
    assert "MERGE (q:Quote {id: row.quote_id})" in query
    assert "MERGE (a:Attribution {id: row.attribution_id})" in query
    assert "MERGE (q)-[:HAS_ATTRIBUTION]->(a)" in query
    assert "a.work_title = row.work_title" in query
    assert "a.page_title = row.page_title" in query
    assert "Work" not in query
    assert "WikiquotePage" not in query
    assert "FOUND_ON" not in query
    assert "FROM_WORK" not in query
    assert "q.normalized_text" not in query
    assert parameters["rows"][0]["author_key"]
    assert parameters["rows"][0]["search_text"] == "a sufficiently long quotation"
    assert set(parameters["rows"][0]) == {
        "quote_id",
        "attribution_id",
        "quote",
        "search_text",
        "quote_type",
        "citation",
        "author_key",
        "author_name",
        "work_title",
        "page_title",
    }


def test_maintenance_cli_has_explicit_graph_commands():
    parser = build_parser()

    assert parser.parse_args(["schema"]).command == "schema"
    assert parser.parse_args(["embed"]).command == "embed"
    assert parser.parse_args(["verify"]).command == "verify"
    with pytest.raises(SystemExit):
        parser.parse_args(["load"])


def test_runtime_search_uses_only_fixed_semantic_index_queries():
    driver = RecordingDriver()
    repository = Neo4jQuoteRepository(driver=driver)

    assert repository.lexical_search("hope + courage", 5) == []
    assert repository.relaxed_lexical_search("hope courage", 5) == []
    assert repository.vector_search([0.0] * 768, 5) == []
    assert repository.fragment_search("to be, or not to be", 5) == []
    assert repository.author_search("Virginia Woolf", 5) == []
    assert repository.autocomplete("to be", 5) == []

    lexical, relaxed, vector, fragment, author, autocomplete = [
        query for query, _ in driver.session_instance.calls
    ]
    assert "db.index.fulltext.queryNodes('quote_text'" in lexical
    assert "db.index.fulltext.queryNodes('quote_text'" in relaxed
    assert driver.session_instance.calls[1][1]["query"] == "hope OR courage"
    assert "VECTOR INDEX quote_embedding" in vector
    assert "SCORE AS score" in vector
    assert "db.index.vector.queryNodes" not in vector
    assert "q.search_text CONTAINS $search_text" in fragment
    assert "db.index.fulltext.queryNodes('author_name'" in author
    assert "q.search_text CONTAINS $search_text" in autocomplete
    assert all("HAS_ATTRIBUTION" in query for query in (lexical, relaxed, vector, fragment, author, autocomplete))
    assert "matched_author.name AS author_name" in author
    assert "matched_attribution.citation AS citation" in author
    assert "matched_attribution.work_title AS work_title" in author
    assert "matched_attribution.page_title AS page_title" in author
    assert all("FOUND_ON" not in query for query in (lexical, relaxed, vector, fragment, author, autocomplete))
    assert all("FROM_WORK" not in query for query in (lexical, relaxed, vector, fragment, author, autocomplete))
    assert "CALL (q)" in lexical
    assert "CALL (q, matched_author)" in author
    assert all("CALL {\n  WITH" not in query for query in (lexical, relaxed, vector, author, autocomplete))


def test_verification_reports_current_graph_and_stale_embeddings():
    repository = Neo4jQuoteRepository(driver=CountDriver())

    counts = repository.verify_counts("gemini-embedding-2", 768)

    assert set(counts) == {
        "Quote",
        "Attribution",
        "Author",
        "quotes_without_current_embedding",
    }
    assert counts["quotes_without_current_embedding"] == 2
    query, parameters = repository.driver.session_instance.calls[-1]
    assert "q.embedding_model <> $model" in query
    assert parameters == {"model": "gemini-embedding-2", "dimensions": 768}


def test_readiness_requires_all_search_indexes_online():
    ready_driver = IndexDriver(4)
    incomplete_driver = IndexDriver(3)

    assert Neo4jQuoteRepository(driver=ready_driver).is_ready() is True
    assert Neo4jQuoteRepository(driver=incomplete_driver).is_ready() is False
    assert ready_driver.connected is True
    assert ready_driver.parameters["names"] == [
        "quote_text",
        "quote_search_text",
        "author_name",
        "quote_embedding",
    ]
