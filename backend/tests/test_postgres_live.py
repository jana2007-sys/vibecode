"""Live PostgreSQL integration smoke test (optional).

Skipped unless ``TEST_PG_URL`` is set to a postgres:// DSN. Verifies the psycopg
adapter can initialize the PostgreSQL schema, run the ``?``-style repository
queries (including the space-separated ``ON CONFLICT`` upserts), and round-trip
a row. Useful to run once against a managed database before deploying.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_PG_URL"),
    reason="set TEST_PG_URL to a postgres:// DSN to run the live PostgreSQL smoke test",
)

from app.database.connection import PostgresDatabase  # noqa: E402
from app.database.repositories.candidate_repository import CandidateRepository  # noqa: E402
from app.models.common import utc_now  # noqa: E402


@pytest.fixture(scope="module")
def pg() -> PostgresDatabase:
    db = PostgresDatabase(os.environ["TEST_PG_URL"])
    db.initialize()
    return db


def test_initialize_and_round_trip(pg: PostgresDatabase) -> None:
    with pg.connection() as conn:
        row = conn.execute("SELECT 1 AS ok").fetchone()
        assert row["ok"] == 1


def test_repository_upsert_and_read(pg: PostgresDatabase) -> None:
    repo = CandidateRepository(pg)
    now = utc_now()
    repo.upsert(
        candidate_id="pg-smoke-1",
        name="Postgres Tester",
        email="pg-smoke@example.com",
        role="Backend Engineer",
        years_of_experience=4.0,
        experience_level="mid",
        skills=[{"name": "Python", "level": "advanced"}],
        learning_journey=[],
        preferred_languages=["Python"],
        focus_areas=["System Design"],
        strengths=[],
        notes="smoke",
        now=now,
    )
    repo.upsert(
        candidate_id="pg-smoke-1",
        name="Postgres Tester",
        email="pg-smoke@example.com",
        role="Backend Engineer",
        years_of_experience=5.0,
        experience_level="mid",
        skills=[{"name": "Python", "level": "advanced"}],
        learning_journey=[],
        preferred_languages=["Python"],
        focus_areas=["System Design"],
        strengths=[],
        notes="smoke",
        now=now,
    )

    row = repo.get_by_id("pg-smoke-1")
    assert row is not None
    assert row["years_of_experience"] == 5.0
    assert row["skills"] == [{"name": "Python", "level": "advanced"}]

    rows = repo.list_all()
    assert any(item["id"] == "pg-smoke-1" for item in rows)
