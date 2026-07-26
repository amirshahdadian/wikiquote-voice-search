from contextlib import contextmanager

from backend.app.cli.maintenance import build_parser
from backend.app.integrations.neo4j_repository import Neo4jQuoteRepository
from backend.app.integrations.neo4j_schema import SCHEMA_STATEMENTS, ensure_schema


class RecordingSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **parameters):
        self.calls.append((cypher, parameters))
        return []


class RecordingDriver:
    def __init__(self):
        self.session_instance = RecordingSession()

    @contextmanager
    def session(self):
        yield self.session_instance

    def close(self):
        return None


def test_schema_has_only_explainable_constraints_and_indexes():
    joined = "\n".join(SCHEMA_STATEMENTS)

    assert "QuoteOccurrence" not in joined
    assert "PrimaryQuote" not in joined
    assert "search_tier" not in joined
    assert "quote_id_unique" in joined
    assert "attribution_id_unique" in joined
    assert "quote_embedding" in joined
    assert "`vector.dimensions`: 768" in joined
    assert "`vector.similarity_function`: 'cosine'" in joined


def test_ensure_schema_executes_every_statement_once():
    session = RecordingSession()

    ensure_schema(session)

    assert [query for query, _ in session.calls] == SCHEMA_STATEMENTS


def test_loader_keeps_provenance_on_attribution_not_quote():
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
    assert "MERGE (a)-[:FOUND_ON]->(p)" in query
    assert "q.primary_author" not in query
    assert parameters["rows"][0]["author_key"]
    assert parameters["rows"][0]["work_key"]


def test_maintenance_cli_has_explicit_graph_commands():
    parser = build_parser()

    assert parser.parse_args(["schema"]).command == "schema"
    assert parser.parse_args(["load"]).command == "load"
    assert parser.parse_args(["embed"]).command == "embed"
    assert parser.parse_args(["verify"]).command == "verify"


def test_runtime_search_uses_only_fixed_semantic_index_queries():
    driver = RecordingDriver()
    repository = Neo4jQuoteRepository(driver=driver)

    assert repository.lexical_search("hope + courage", 5) == []
    assert repository.vector_search([0.0] * 768, 5) == []
    assert repository.author_search("Virginia Woolf", 5) == []
    assert repository.autocomplete("to be", 5) == []

    lexical, vector, author, autocomplete = [
        query for query, _ in driver.session_instance.calls
    ]
    assert "db.index.fulltext.queryNodes('quote_text'" in lexical
    assert "db.index.vector.queryNodes('quote_embedding'" in vector
    assert "db.index.fulltext.queryNodes('author_name'" in author
    assert "db.index.fulltext.queryNodes('quote_text'" in autocomplete
    assert all("HAS_ATTRIBUTION" in query for query in (lexical, vector, author, autocomplete))
