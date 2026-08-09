"""Schema compatibility tests.

The repository layer is backend-agnostic, so the SQLite and PostgreSQL DDL files
must stay in sync. These tests parse both pairs of schema files and assert they
describe the same tables and columns (only the SQLite REAL affinity is allowed
to become DOUBLE PRECISION). They also sanity-check the upsert SQL that must be
valid on both backends.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.database.connection import (
    Database,
    PostgresDatabase,
    _split_statements,
    _translate_sql,
    create_database,
)
from app.utils.config import Settings

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "app" / "database"

# SQLite type affinity -> equivalent PostgreSQL type
TYPE_MAP = {"REAL": "DOUBLE PRECISION"}


def _normalise_type(declared: str) -> str:
    """Map a SQLite affinity to its PostgreSQL equivalent (uppercased)."""
    return TYPE_MAP.get(declared.upper(), declared.upper())


def _parse_schema(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Return {table: [(column, normalised_type), ...]} in declared order."""
    text = path.read_text(encoding="utf-8")
    tables: dict[str, list[tuple[str, str]]] = {}
    # Each CREATE TABLE ... ( ... ) block. Matches nested CHECK parentheses by
    # balancing; the schemas never nest deeper, so a simple balance scan works.
    for match in re.finditer(
        r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)\s*\((.*?)\)\s*;",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        name = match.group(1)
        body = match.group(2)
        columns: list[tuple[str, str]] = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith("CREATE"):
                continue
            col = re.match(r"^(\w+)\s+(TEXT|INTEGER|REAL|DOUBLE PRECISION)\b", line, re.IGNORECASE)
            if col:
                columns.append((col.group(1), _normalise_type(col.group(2))))
        tables[name] = columns
    return tables


@pytest.mark.parametrize(
    ("sqlite_file", "postgres_file"),
    [
        ("schema.sql", "schema_postgres.sql"),
        ("private_schema.sql", "private_schema_postgres.sql"),
    ],
)
def test_postgres_schema_mirrors_sqlite(sqlite_file: str, postgres_file: str) -> None:
    sqlite = _parse_schema(SCHEMA_DIR / sqlite_file)
    postgres = _parse_schema(SCHEMA_DIR / postgres_file)

    assert set(postgres) == set(sqlite), "table sets differ between dialects"

    for table in sqlite:
        assert postgres[table] == sqlite[table], (
            f"column set/order/types differ for {table!r} "
            f"({sqlite_file} vs {postgres_file})"
        )


def test_postgres_schema_is_parseable() -> None:
    """Guard against obvious DDL typos: every CREATE TABLE must parse."""
    sqlite = _parse_schema(SCHEMA_DIR / "schema.sql")
    postgres = _parse_schema(SCHEMA_DIR / "schema_postgres.sql")
    expected = {
        "candidates",
        "sessions",
        "messages",
        "scores",
        "feedback",
    }
    assert set(sqlite) == expected
    assert set(postgres) == expected

    private = _parse_schema(SCHEMA_DIR / "private_schema_postgres.sql")
    assert set(private) == {"enrolled_candidates", "enrolled_reports"}


def test_create_database_defaults_to_sqlite() -> None:
    db = create_database(Settings(database_url="", database_path="data/t.db"))
    assert isinstance(db, Database)
    assert db.backend == "sqlite"
    assert db.schema == "schema.sql"


def test_create_database_picks_postgres_on_dsn() -> None:
    db = create_database(Settings(database_url="postgres://u:p@h:5432/d"))
    assert isinstance(db, PostgresDatabase)
    assert db.backend == "postgres"
    assert db.schema == "schema_postgres.sql"


def test_create_private_database_picks_postgres_on_dsn() -> None:
    db = create_database(Settings(database_url="postgresql://u:p@h:5432/d"), private=True)
    assert isinstance(db, PostgresDatabase)
    assert db.schema == "private_schema_postgres.sql"


def test_translate_sql_rewrites_placeholders() -> None:
    assert _translate_sql("WHERE id = ? AND n = ?") == "WHERE id = %s AND n = %s"
    assert _translate_sql("VALUES (?, ?, ?)") == "VALUES (%s, %s, %s)"


def test_split_statements_strips_comments() -> None:
    script = (
        "-- header comment\n"
        "CREATE TABLE a (id TEXT PRIMARY KEY);\n"
        "CREATE INDEX idx ON a(id);\n"
    )
    statements = _split_statements(script)
    assert statements == ["CREATE TABLE a (id TEXT PRIMARY KEY)", "CREATE INDEX idx ON a(id)"]


def test_upsert_syntax_is_standard() -> None:
    """ON CONFLICT with a space is valid on SQLite AND PostgreSQL."""
    repo_dir = SCHEMA_DIR / "repositories"
    for path in sorted(repo_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "ON CONFLICT(id)" not in text, (
            f"{path.name}: compact 'ON CONFLICT(id)' is invalid on PostgreSQL"
        )
        if "ON CONFLICT" not in text:
            continue
        assert "ON CONFLICT (id)" in text or "ON CONFLICT (session_id)" in text, (
            f"{path.name}: expected a space-separated ON CONFLICT upsert"
        )
