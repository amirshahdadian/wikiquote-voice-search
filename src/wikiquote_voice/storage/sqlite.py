"""SQLite storage utilities for the Wikiquote Voice Search project."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional

from ..config import Config

DEFAULT_DB_PATH = Config.DB_PATH


def _ensure_parent_directory(db_path: Path) -> None:
    """Ensure the directory for the SQLite database exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return a SQLite connection with foreign key support enabled."""
    database_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    _ensure_parent_directory(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def initialize_database(db_path: Optional[Path] = None) -> Path:
    """Create required tables if they do not already exist."""
    database_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    _ensure_parent_directory(database_path)

    table_statements: Dict[str, str] = {
        "users": """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,
        "embeddings": """
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content_hash TEXT NOT NULL,
                embedding BLOB NOT NULL,
                model TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
        """,
        "preferences": """
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                preference_key TEXT NOT NULL,
                preference_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, preference_key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """,
        "favorites": """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                quote_id TEXT NOT NULL,
                quote_text TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, quote_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """,
        "history": """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                payload TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
        """,
        "enrollment_samples": """
            CREATE TABLE IF NOT EXISTS enrollment_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                audio_path TEXT NOT NULL,
                embedding_id INTEGER,
                duration REAL,
                rms REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, audio_path),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (embedding_id) REFERENCES embeddings(id) ON DELETE SET NULL
            );
        """,
        "favorite_media": """
            CREATE TABLE IF NOT EXISTS favorite_media (
                favorite_id INTEGER PRIMARY KEY,
                audio_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (favorite_id) REFERENCES favorites(id) ON DELETE CASCADE
            );
        """,
        "session_metrics": """
            CREATE TABLE IF NOT EXISTS session_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                input_path TEXT,
                output_path TEXT,
                asr_ms REAL,
                sid_ms REAL,
                search_ms REAL,
                tts_ms REAL,
                similarity REAL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
        """,
    }

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        cursor = connection.cursor()
        for statement in _iter_table_statements(table_statements):
            cursor.execute(statement)
        connection.commit()

    return database_path


def _iter_table_statements(statements: Dict[str, str]) -> Iterable[str]:
    """Yield normalized SQL statements from the supplied mapping."""
    for _name, statement in statements.items():
        normalized = " ".join(line.strip() for line in statement.strip().splitlines())
        yield normalized


__all__ = ["DEFAULT_DB_PATH", "get_connection", "initialize_database"]
