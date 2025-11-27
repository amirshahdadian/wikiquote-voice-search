"""Storage helpers for Wikiquote voice search."""

from .sqlite import DEFAULT_DB_PATH, get_connection, initialize_database

__all__ = ["DEFAULT_DB_PATH", "get_connection", "initialize_database"]
