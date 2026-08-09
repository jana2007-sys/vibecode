"""Database connection management (SQLite + PostgreSQL).

A single ``Database`` instance owns the connection factory. Repositories receive
it via DI and open short-lived connections per operation, which is the safe
pattern under FastAPI's thread pool (no shared connection across threads).

``Database`` is the local SQLite backend (the default). ``PostgresDatabase``
implements the exact same ``connection()``/``initialize()`` surface over
psycopg, so repositories never know which backend they are talking to. The
backend is chosen from the ``DATABASE_URL`` setting: a postgres:// URL selects
PostgreSQL, otherwise SQLite keeps working for local development.
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


def _is_postgres_url(url: str) -> bool:
    """Return True for a PostgreSQL DSN (postgres:// or postgresql://)."""
    return url.startswith("postgres://") or url.startswith("postgresql://")


def _translate_sql(sql: str) -> str:
    """Rewrite SQLite ``?`` placeholders to psycopg ``%s`` placeholders.

    The repository layer writes ``?`` placeholders (SQLite native). PostgreSQL
    uses ``%s``; none of the project's SQL contains a literal ``?``, so a simple
    replace is safe.
    """
    return sql.replace("?", "%s")


def _split_statements(script: str) -> list[str]:
    """Split a DDL script into single executable statements.

    Strips ``--`` line comments and splits on ``;``. Suitable for the project's
    plain ``CREATE TABLE`` / ``CREATE INDEX`` scripts (no stored procedures or
    string literals containing semicolons).
    """
    body = "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("--")
    )
    return [chunk.strip() for chunk in body.split(";") if chunk.strip()]


class Database:
    """Thin wrapper around SQLite exposing connection + initialization."""

    backend = "sqlite"

    def __init__(self, db_path: Path, schema: str = "schema.sql") -> None:
        self.db_path = db_path
        self.schema = schema

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
        """Create tables from the schema file if they do not exist yet."""
        schema_path = Path(__file__).resolve().parent / self.schema
        with self.connection() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
        logger.info("Database initialized at %s", self.db_path)


class _PostgresConnection:
    """Minimal psycopg adapter exposing the repository-facing connection API.

    Repositories only rely on ``execute`` (chaining ``fetchone``/``fetchall``/
    ``rowcount`` on the returned cursor) plus ``executescript``/``commit``/
    ``rollback``/``close``. psycopg already satisfies these; this adapter only
    rewrites ``?`` placeholders to psycopg's ``%s`` style.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql: str, params: object = None):
        return self._conn.execute(_translate_sql(sql), params)

    def executescript(self, script: str) -> None:
        for statement in _split_statements(script):
            self._conn.execute(_translate_sql(statement))

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class PostgresDatabase(Database):
    """PostgreSQL-backed database exposing the same repository interface.

    Each ``connection()`` opens a fresh psycopg connection (matching the
    SQLite pattern of short-lived connections), so there is no shared state
    across threads.
    """

    backend = "postgres"

    def __init__(self, dsn: str, schema: str = "schema_postgres.sql") -> None:
        self.dsn = dsn
        self.schema = schema

    @contextmanager
    def connection(self) -> Iterator[_PostgresConnection]:
        """Yield a psycopg connection adapter; always commits/closes it."""
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(self.dsn, row_factory=dict_row)
        wrapper = _PostgresConnection(conn)
        try:
            yield wrapper
            wrapper.commit()
        except Exception:
            wrapper.rollback()
            raise
        finally:
            wrapper.close()

    def initialize(self) -> None:
        """Create tables from the PostgreSQL schema file if missing."""
        schema_path = Path(__file__).resolve().parent / self.schema
        statements = _split_statements(schema_path.read_text(encoding="utf-8"))
        with self.connection() as conn:
            for statement in statements:
                conn.execute(statement)
        logger.info("PostgreSQL database initialized")


def create_database(settings, *, private: bool = False) -> Database:
    """Build the Database instance for ``settings`` (SQLite or PostgreSQL).

    When ``DATABASE_URL`` points at PostgreSQL the private archive shares the
    same PostgreSQL instance (separate tables); otherwise each uses its own
    SQLite file.
    """
    from app.utils.config import Settings

    if not isinstance(settings, Settings):
        settings = Settings(**settings) if isinstance(settings, dict) else settings

    if _is_postgres_url(settings.database_url):
        schema = "private_schema_postgres.sql" if private else "schema_postgres.sql"
        return PostgresDatabase(settings.database_url, schema=schema)
    path = settings.private_database_file_path if private else settings.database_file_path
    schema = "private_schema.sql" if private else "schema.sql"
    return Database(path, schema=schema)


_db: Database | None = None


def get_database() -> Database:
    """Return the singleton Database instance (constructed on first use)."""
    global _db
    if _db is None:
        from app.utils.config import get_settings

        _db = create_database(get_settings())
    return _db


_private_db: Database | None = None


def get_private_database() -> Database:
    """Return the singleton private Database instance (constructed on first use).

    The private database archives enrolled candidates and their completed
    interview reports. It is intentionally isolated from the public tables
    used by the API; in production it lives in the same PostgreSQL instance
    but in its own tables.
    """
    global _private_db
    if _private_db is None:
        from app.utils.config import get_settings

        _private_db = create_database(get_settings(), private=True)
    return _private_db


def reset_database_singletons() -> None:
    """Drop the cached singletons (used by tests)."""
    global _db, _private_db
    _db = None
    _private_db = None
