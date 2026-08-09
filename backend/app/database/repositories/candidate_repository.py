"""Repository for the ``candidates`` table."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.database.repositories.base import BaseRepository


class CandidateRepository(BaseRepository):
    """Persistence for candidate profiles."""

    table = "candidates"

    def upsert(
        self,
        candidate_id: str,
        *,
        name: str,
        email: str | None,
        role: str,
        years_of_experience: float,
        experience_level: str,
        skills: list[dict],
        learning_journey: list[dict],
        preferred_languages: list[str],
        focus_areas: list[str],
        strengths: list[str],
        notes: str,
        now: datetime,
    ) -> None:
        """Insert a candidate, or update the existing row with the same id."""
        with self._db.connection() as conn:
            conn.execute(
                """
                INSERT INTO candidates (
                    id, name, email, role, years_of_experience, experience_level,
                    skills, learning_journey, preferred_languages, focus_areas,
                    strengths, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    name = excluded.name,
                    email = COALESCE(excluded.email, candidates.email),
                    role = excluded.role,
                    years_of_experience = excluded.years_of_experience,
                    experience_level = excluded.experience_level,
                    skills = excluded.skills,
                    learning_journey = excluded.learning_journey,
                    preferred_languages = excluded.preferred_languages,
                    focus_areas = excluded.focus_areas,
                    strengths = excluded.strengths,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate_id,
                    name,
                    email,
                    role,
                    years_of_experience,
                    experience_level,
                    self._dumps(skills),
                    self._dumps(learning_journey),
                    self._dumps(preferred_languages),
                    self._dumps(focus_areas),
                    self._dumps(strengths),
                    notes,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

    def get_by_email(self, email: str) -> dict | None:
        """Return the candidate row with the given email, if it exists."""
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM candidates WHERE email = ?",
                (email,),
            ).fetchone()
        return self._hydrate(row)

    def get_by_id(self, record_id: str) -> dict | None:
        """Fetch a single candidate row by primary key, or None (JSON decoded)."""
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM candidates WHERE id = ?",
                (record_id,),
            ).fetchone()
        return self._hydrate(row)

    def list_all(self) -> list[dict]:
        """Return all candidates ordered by name."""
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM candidates ORDER BY name ASC").fetchall()
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: dict | None) -> dict | None:
        """Decode the JSON columns of a candidate row."""
        if row is None:
            return None
        row["skills"] = self._loads(row.get("skills"), [])
        row["learning_journey"] = self._loads(row.get("learning_journey"), [])
        row["preferred_languages"] = self._loads(row.get("preferred_languages"), [])
        row["focus_areas"] = self._loads(row.get("focus_areas"), [])
        row["strengths"] = self._loads(row.get("strengths"), [])
        return row
