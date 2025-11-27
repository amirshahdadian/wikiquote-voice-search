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
        "user_tts_preferences": """
            CREATE TABLE IF NOT EXISTS user_tts_preferences (
                user_id TEXT PRIMARY KEY,
                pitch_scale REAL DEFAULT 1.0,
                speaking_rate REAL DEFAULT 1.0,
                energy_scale REAL DEFAULT 1.0,
                style TEXT DEFAULT 'neutral',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


# TTS Preferences Helper Functions
def save_tts_preferences(user_id: str, preferences: Dict, db_path: Optional[Path] = None) -> bool:
    """
    Save or update TTS preferences for a user
    
    Args:
        user_id: User identifier
        preferences: Dictionary with pitch_scale, speaking_rate, energy_scale, style
        db_path: Optional database path
        
    Returns:
        True if successful
    """
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO user_tts_preferences 
            (user_id, pitch_scale, speaking_rate, energy_scale, style, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                pitch_scale = excluded.pitch_scale,
                speaking_rate = excluded.speaking_rate,
                energy_scale = excluded.energy_scale,
                style = excluded.style,
                updated_at = datetime('now')
        """, (
            user_id,
            preferences.get('pitch_scale', 1.0),
            preferences.get('speaking_rate', 1.0),
            preferences.get('energy_scale', 1.0),
            preferences.get('style', 'neutral')
        ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error saving TTS preferences: {e}")
        return False


def get_tts_preferences(user_id: str, db_path: Optional[Path] = None) -> Optional[Dict]:
    """
    Get TTS preferences for a user
    
    Args:
        user_id: User identifier
        db_path: Optional database path
        
    Returns:
        Dictionary of preferences or None if not found
    """
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pitch_scale, speaking_rate, energy_scale, style
            FROM user_tts_preferences
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'pitch_scale': row[0],
                'speaking_rate': row[1],
                'energy_scale': row[2],
                'style': row[3]
            }
        return None
        
    except Exception as e:
        print(f"Error getting TTS preferences: {e}")
        return None


def create_user(user_id: str, db_path: Optional[Path] = None) -> bool:
    """
    Create a new user entry
    
    Args:
        user_id: User identifier (will be used as username)
        db_path: Optional database path
        
    Returns:
        True if successful
    """
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR IGNORE INTO users (username)
            VALUES (?)
        """, (user_id,))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error creating user: {e}")
        return False


def user_exists(user_id: str, db_path: Optional[Path] = None) -> bool:
    """
    Check if a user exists
    
    Args:
        user_id: User identifier
        db_path: Optional database path
        
    Returns:
        True if user exists
    """
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM users WHERE username = ?
        """, (user_id,))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0
        
    except Exception as e:
        print(f"Error checking user: {e}")
        return False


def list_all_users(db_path: Optional[Path] = None) -> list:
    """
    List all users in the database
    
    Args:
        db_path: Optional database path
        
    Returns:
        List of usernames
    """
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT username FROM users ORDER BY created_at DESC
        """)
        
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return users
        
    except Exception as e:
        print(f"Error listing users: {e}")
        return []


__all__ = [
    "DEFAULT_DB_PATH", 
    "get_connection", 
    "initialize_database",
    "save_tts_preferences",
    "get_tts_preferences",
    "create_user",
    "user_exists",
    "list_all_users"
]
