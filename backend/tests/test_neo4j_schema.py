import pytest

from backend.maintenance import build_parser
from backend.neo4j import Neo4jQuoteRepository
from backend.neo4j import SCHEMA_STATEMENTS, _status_rank, ensure_schema


class RecordingDriver:
    """Stands in for a Neo4j driver, capturing what execute_query is asked to run."""

    def __init__(self, records=None):
        self.calls: list[tuple[str, dict]] = []
        self.records = records or []
        self.connected = False

    def execute_query(self, query, parameters=None, **kwargs):
        self.calls.append((query, {**(parameters or {}), **kwargs}))
        return self.records, None, None

    def verify_connectivity(self):
        self.connected = True

    def close(self):
        return None


def test_schema_has_only_explainable_constraints_and_indexes():
    joined = "\n".join(SCHEMA_STATEMENTS)

    assert "quote_id_unique" in joined
    assert "attribution_id_unique" in joined
    assert "author_key_unique" in joined
    assert "work_key_unique" not in joined
    assert "wikiquote_page_id_unique" not in joined
    assert "quote_search_text" in joined
    assert "q.normalized_text" not in joined
    assert "quote_embedding" not in joined


def test_ensure_schema_executes_every_statement_once():
    driver = RecordingDriver()

    ensure_schema(driver)

    assert [query for query, _ in driver.calls] == SCHEMA_STATEMENTS


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

    query, parameters = driver.calls[0]
    assert "MERGE (q:Quote {id: row.quote_id})" in query
    assert "MERGE (a:Attribution {id: row.attribution_id})" in query
    assert "MERGE (q)-[:HAS_ATTRIBUTION]->(a)" in query
    assert "a.work_title = row.work_title" in query
    assert "a.status_rank = row.status_rank" in query
    assert "a.page_title = row.page_title" in query
    assert "Work" not in query
    assert "WikiquotePage" not in query
    assert "FOUND_ON" not in query
    assert "FROM_WORK" not in query
    assert "q.normalized_text" not in query
    assert parameters["rows"][0]["author_key"]
    assert parameters["rows"][0]["search_text"] == "a sufficiently long quotation"
    assert parameters["rows"][0]["status_rank"] == 0
    assert set(parameters["rows"][0]) == {
        "quote_id",
        "attribution_id",
        "quote",
        "search_text",
        "quote_type",
        "status_rank",
        "citation",
        "author_key",
        "author_name",
        "work_title",
        "page_title",
    }


def test_claim_preference_is_stored_as_data_not_query_logic():
    assert [_status_rank(s) for s in ("sourced", "attributed", "disputed", "about")] == [
        0,
        1,
        2,
        3,
    ]
    assert _status_rank("something Wikiquote has not used before") == 3
    assert all("CASE" not in query for query in SCHEMA_STATEMENTS)


def test_maintenance_cli_has_explicit_graph_commands():
    parser = build_parser()

    assert parser.parse_args(["verify"]).command == "verify"
    for removed in ("load", "embed", "schema"):
        with pytest.raises(SystemExit):
            parser.parse_args([removed])


def test_runtime_search_uses_only_fixed_index_queries():
    driver = RecordingDriver()
    repository = Neo4jQuoteRepository(driver=driver)

    assert repository.lexical_search("hope + courage", 5) == []
    assert repository.author_topic_search("imagination", "Einstein", 5) == []
    assert repository.fragment_search("to be, or not to be", 5) == []
    assert repository.author_search("Virginia Woolf", 5) == []

    lexical, author_topic, fragment, author = [query for query, _ in driver.calls]
    every = (lexical, author_topic, fragment, author)
    assert "db.index.fulltext.queryNodes('quote_text'" in lexical
    assert "db.index.fulltext.queryNodes('quote_text'" in author_topic
    assert "toLower(author.name) CONTAINS toLower($name)" in author_topic
    assert "q.search_text CONTAINS $search_text" in fragment
    assert "db.index.fulltext.queryNodes('author_name'" in author
    assert all("HAS_ATTRIBUTION" in query for query in every)
    assert "author.name AS author_name" in author
    assert "attribution.citation AS citation" in author
    assert "attribution.work_title AS work_title" in author
    assert "attribution.page_title AS page_title" in author
    assert all("FOUND_ON" not in query for query in every)
    assert all("FROM_WORK" not in query for query in every)
    assert all("quote_embedding" not in query for query in every)
    assert "CALL (q)" in lexical
    assert all("CALL {\n  WITH" not in query for query in every)


def test_no_query_ranks_claims_or_walks_a_path_twice():
    """The claim order is a stored property, so no query re-derives it."""
    driver = RecordingDriver()
    repository = Neo4jQuoteRepository(driver=driver)

    repository.lexical_search("hope", 5)
    repository.author_topic_search("hope", "Einstein", 5)
    repository.author_search("Virginia Woolf", 5)
    repository.fragment_search("to be", 5)
    repository.random_quote()

    for query, _ in driver.calls:
        assert "CASE" not in query
        assert query.count("ATTRIBUTED_TO") <= 1
        assert "status_rank" in query or "ATTRIBUTED_TO" not in query


def test_request_terms_are_optional_and_name_terms_are_required():
    driver = RecordingDriver()
    repository = Neo4jQuoteRepository(driver=driver)

    repository.lexical_search("how do i be brave when scared", 5)
    repository.author_search("Virginia Woolf", 5)

    lexical_parameters, author_parameters = [
        parameters for _, parameters in driver.calls
    ]
    assert lexical_parameters["query"] == "how OR do OR i OR be OR brave OR when OR scared"
    assert author_parameters["query"] == "Virginia AND Woolf"


def test_verification_reports_current_graph_counts():
    repository = Neo4jQuoteRepository(driver=RecordingDriver([{"count": 7}]))

    assert repository.verify_counts() == {"Quote": 7, "Attribution": 7, "Author": 7}


def test_readiness_requires_all_search_indexes_online():
    ready = RecordingDriver([{"online": 3}])
    incomplete = RecordingDriver([{"online": 2}])

    assert Neo4jQuoteRepository(driver=ready).is_ready() is True
    assert Neo4jQuoteRepository(driver=incomplete).is_ready() is False
    assert ready.connected is True
    assert ready.calls[0][1]["names"] == [
        "quote_text",
        "quote_search_text",
        "author_name",
    ]


def test_topic_search_weights_by_speaker_and_keeps_one_quote_each():
    driver = RecordingDriver()
    repository = Neo4jQuoteRepository(driver=driver)

    repository.lexical_search("courage bravery", 5)

    query, parameters = driver.calls[0]
    assert "speaker_weight" in query
    assert "100.0 + speaker_weight" in query
    assert "coalesce(author_name, quote_id) AS speaker" in query
    assert parameters["candidate_limit"] == 1500


def test_only_topic_search_is_reweighted():
    """Author and fragment results have one speaker or exact wording already."""
    driver = RecordingDriver()
    repository = Neo4jQuoteRepository(driver=driver)

    repository.author_search("Virginia Woolf", 5)
    repository.fragment_search("to be", 5)
    repository.random_quote()

    for query, _ in driver.calls:
        assert "speaker_weight) " not in query.replace("coalesce", "")
