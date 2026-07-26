"""SQLite storage for user names and Kokoro preferences."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from backend.app.core.settings import settings

logger = logging.getLogger(__name__)
DEFAULT_DB_PATH = settings.resolved_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    group_identifier TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_tts_preferences (
    user_id TEXT PRIMARY KEY REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    pitch_scale REAL NOT NULL DEFAULT 1.0,
    speaking_rate REAL NOT NULL DEFAULT 1.0,
    energy_scale REAL NOT NULL DEFAULT 1.0,
    style TEXT NOT NULL DEFAULT 'neutral',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path | None = None) -> Path:
    path = Path(db_path or DEFAULT_DB_PATH)
    with get_connection(path) as connection:
        connection.executescript(_SCHEMA)
    return path


def save_user_profile(
    user_id: str,
    display_name: str,
    group_identifier: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_profiles (
                    user_id, display_name, group_identifier
                ) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    group_identifier = excluded.group_identifier,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, display_name, group_identifier),
            )
        return True
    except sqlite3.Error:
        logger.exception("Could not save user profile")
        return False


def get_user_profile(
    user_id: str, db_path: Path | None = None
) -> dict[str, Any] | None:
    try:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT user_id, display_name, group_identifier,
                       created_at, updated_at
                FROM user_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        logger.exception("Could not load user profile")
        return None


def list_user_profiles(db_path: Path | None = None) -> list[dict[str, Any]]:
    try:
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT user_id, display_name, group_identifier,
                       created_at, updated_at
                FROM user_profiles
                ORDER BY display_name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        logger.exception("Could not list user profiles")
        return []


def delete_user_profile(user_id: str, db_path: Path | None = None) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                "DELETE FROM user_profiles WHERE user_id = ?", (user_id,)
            )
        return True
    except sqlite3.Error:
        logger.exception("Could not delete user profile")
        return False


def save_tts_preferences(
    user_id: str,
    preferences: dict[str, Any],
    db_path: Path | None = None,
) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_tts_preferences (
                    user_id, pitch_scale, speaking_rate, energy_scale, style
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    pitch_scale = excluded.pitch_scale,
                    speaking_rate = excluded.speaking_rate,
                    energy_scale = excluded.energy_scale,
                    style = excluded.style,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    preferences.get("pitch_scale", 1.0),
                    preferences.get("speaking_rate", 1.0),
                    preferences.get("energy_scale", 1.0),
                    preferences.get("style", "neutral"),
                ),
            )
        return True
    except sqlite3.Error:
        logger.exception("Could not save TTS preferences")
        return False


def get_tts_preferences(
    user_id: str, db_path: Path | None = None
) -> dict[str, Any] | None:
    try:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT pitch_scale, speaking_rate, energy_scale, style
                FROM user_tts_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        logger.exception("Could not load TTS preferences")
        return None


def delete_tts_preferences(
    user_id: str, db_path: Path | None = None
) -> bool:
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                "DELETE FROM user_tts_preferences WHERE user_id = ?",
                (user_id,),
            )
        return True
    except sqlite3.Error:
        logger.exception("Could not delete TTS preferences")
        return False


def list_tts_preference_users(db_path: Path | None = None) -> list[str]:
    try:
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT user_id
                FROM user_tts_preferences
                ORDER BY user_id COLLATE NOCASE
                """
            ).fetchall()
        return [row["user_id"] for row in rows]
    except sqlite3.Error:
        logger.exception("Could not list TTS preference users")
        return []
