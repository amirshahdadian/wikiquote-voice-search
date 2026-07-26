from __future__ import annotations

from typing import Any


SCHEMA_STATEMENTS = [
    """
    CREATE CONSTRAINT quote_id_unique IF NOT EXISTS
    FOR (q:Quote) REQUIRE q.id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT attribution_id_unique IF NOT EXISTS
    FOR (a:Attribution) REQUIRE a.id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT author_key_unique IF NOT EXISTS
    FOR (a:Author) REQUIRE a.key IS UNIQUE
    """,
    """
    CREATE CONSTRAINT work_key_unique IF NOT EXISTS
    FOR (w:Work) REQUIRE w.key IS UNIQUE
    """,
    """
    CREATE CONSTRAINT wikiquote_page_id_unique IF NOT EXISTS
    FOR (p:WikiquotePage) REQUIRE p.id IS UNIQUE
    """,
    """
    CREATE FULLTEXT INDEX quote_text IF NOT EXISTS
    FOR (q:Quote) ON EACH [q.text, q.normalized_text]
    OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}
    """,
    """
    CREATE FULLTEXT INDEX author_name IF NOT EXISTS
    FOR (a:Author) ON EACH [a.name]
    """,
    """
    CREATE VECTOR INDEX quote_embedding IF NOT EXISTS
    FOR (q:Quote) ON q.embedding
    OPTIONS {indexConfig: {
      `vector.dimensions`: 768,
      `vector.similarity_function`: 'cosine'
    }}
    """,
]


def ensure_schema(session: Any) -> None:
    for statement in SCHEMA_STATEMENTS:
        session.run(statement)
