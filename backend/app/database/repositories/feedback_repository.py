"""Repository for the ``feedback`` table."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.base import BaseRepository


class FeedbackRepository(BaseRepository):
    """Persistence for structured interview reports."""

    table = "feedback"

    def create(
        self,
        feedback_id: str,
        session_id: str,
        overall_score: float,
        summary: str,
        strengths: list[str],
        improvements: list[str],
        topics: list[dict],
        created_at: datetime,
        source: str = "deterministic",
    ) -> None:
        """Insert a feedback report for a session (one report per session)."""
        with self._db.connection() as conn:
            conn.execute(
                """
                INSERT INTO feedback (id, session_id, overall_score, summary, strengths, improvements, topics, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    session_id,
                    overall_score,
                    summary,
                    self._dumps(strengths),
                    self._dumps(improvements),
                    self._dumps(topics),
                    created_at.isoformat(),
                    source,
                ),
            )

    def get_by_session(self, session_id: str) -> dict | None:
        """Return the feedback report for a session, if it exists."""
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM feedback WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        row["strengths"] = self._loads(row["strengths"], [])
        row["improvements"] = self._loads(row["improvements"], [])
        row["topics"] = self._loads(row["topics"], [])
        return row
