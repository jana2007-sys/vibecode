"""Repository for the private archive tables (enrolled_candidates/reports)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.database.repositories.base import BaseRepository


class EnrollmentRepository(BaseRepository):
    """Persistence for the private enrollment archive.

    Mirrors the candidate columns so the archived snapshot is independent of the
    public ``candidates`` table (which can be edited or deleted) and stores the
    full report JSON so every completed interview is recoverable.
    """

    table = "enrolled_candidates"

    def store(self, candidate: dict, report: dict, now: datetime) -> None:
        """Upsert an enrolled candidate snapshot and their completed report."""
        with self._db.connection() as conn:
            conn.execute(
                """
                INSERT INTO enrolled_candidates (
                    id, name, email, role, years_of_experience, experience_level,
                    skills, learning_journey, preferred_languages, focus_areas,
                    strengths, notes, enrolled_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    name = excluded.name,
                    email = COALESCE(excluded.email, enrolled_candidates.email),
                    role = excluded.role,
                    years_of_experience = excluded.years_of_experience,
                    experience_level = excluded.experience_level,
                    skills = excluded.skills,
                    learning_journey = excluded.learning_journey,
                    preferred_languages = excluded.preferred_languages,
                    focus_areas = excluded.focus_areas,
                    strengths = excluded.strengths,
                    notes = excluded.notes
                """,
                (
                    candidate["id"],
                    candidate["name"],
                    candidate.get("email"),
                    candidate.get("role", ""),
                    candidate.get("years_of_experience", 0.0),
                    candidate.get("experience_level", "mid"),
                    self._dumps(candidate.get("skills", [])),
                    self._dumps(candidate.get("learning_journey", [])),
                    self._dumps(candidate.get("preferred_languages", [])),
                    self._dumps(candidate.get("focus_areas", [])),
                    self._dumps(candidate.get("strengths", [])),
                    candidate.get("notes", ""),
                    now.isoformat(),
                ),
            )
            conn.execute(
                """
                INSERT INTO enrolled_reports (session_id, candidate_id, report, completed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (session_id) DO UPDATE SET
                    candidate_id = excluded.candidate_id,
                    report = excluded.report,
                    completed_at = excluded.completed_at
                """,
                (
                    report["session_id"],
                    candidate["id"],
                    self._dumps(report),
                    now.isoformat(),
                ),
            )

    def get_candidate(self, candidate_id: str) -> dict | None:
        """Return one archived candidate snapshot, or None."""
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM enrolled_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return self._hydrate_candidate(row)

    def list_reports(self, candidate_id: str | None = None) -> list[dict]:
        """Return archived reports, newest first, optionally for one candidate."""
        where = "WHERE candidate_id = ?" if candidate_id else ""
        params: tuple[Any, ...] = (candidate_id,) if candidate_id else ()
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM enrolled_reports {where} ORDER BY completed_at DESC",
                params,
            ).fetchall()
        return [self._hydrate_report(row) for row in rows]

    def list_enrollments(self) -> list[dict]:
        """Return every archived candidate with their reports, newest first."""
        with self._db.connection() as conn:
            candidates = conn.execute(
                "SELECT * FROM enrolled_candidates ORDER BY enrolled_at DESC"
            ).fetchall()
        reports = self.list_reports()
        by_candidate: dict[str, list[dict]] = {}
        for report in reports:
            by_candidate.setdefault(report["candidate_id"], []).append(report)
        return [
            {**self._hydrate_candidate(row), "reports": by_candidate.get(row["id"], [])}
            for row in candidates
        ]

    @staticmethod
    def _hydrate_candidate(row: dict | None) -> dict | None:
        """Decode the JSON columns of an enrolled candidate row."""
        if row is None:
            return None
        row["skills"] = BaseRepository.loads_json(row.get("skills"), [])
        row["learning_journey"] = BaseRepository.loads_json(row.get("learning_journey"), [])
        row["preferred_languages"] = BaseRepository.loads_json(row.get("preferred_languages"), [])
        row["focus_areas"] = BaseRepository.loads_json(row.get("focus_areas"), [])
        row["strengths"] = BaseRepository.loads_json(row.get("strengths"), [])
        return row

    @staticmethod
    def _hydrate_report(row: dict) -> dict:
        """Decode the report JSON of an enrolled report row."""
        row["report"] = BaseRepository.loads_json(row.get("report"), {})
        return row
