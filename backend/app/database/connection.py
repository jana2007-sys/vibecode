"""SQLite connection management.

A single ``Database`` instance owns the connection factory. Repositories receive
it via DI and open short-lived connections per operation, which is the safe
pattern for SQLite under FastAPI's thread pool (no shared connection across
threads).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.utils.logging import get_logger

logger = get_logger(__name__)


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    """Return rows as dicts keyed by column name."""
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


class Database:
    """Thin wrapper around SQLite exposing connection + initialization."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a new connection with sane defaults; always closes it."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = _dict_factory
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create tables from schema.sql if they do not exist yet."""
        schema_path = Path(__file__).resolve().parent / "schema.sql"
        with self.connection() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
        logger.info("Database initialized at %s", self.db_path)


_db: Database | None = None


def get_database() -> Database:
    """Return the singleton Database instance (constructed on first use)."""
    global _db
    if _db is None:
        from app.utils.config import get_settings

        _db = Database(get_settings().database_file_path)
    return _db
