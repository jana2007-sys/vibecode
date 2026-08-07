"""Repository for the ``scores`` table."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.base import BaseRepository


class ScoreRepository(BaseRepository):
    """Persistence for per-question / per-topic evaluation scores."""

    table = "scores"

    def create(
        self,
        score_id: str,
        session_id: str,
        topic_id: str,
        question_id: str,
        score: float,
        rationale: str,
        created_at: datetime,
    ) -> None:
        """Insert a single evaluation score record."""
        with self._db.connection() as conn:
            conn.execute(
                """
                INSERT INTO scores (id, session_id, topic_id, question_id, score, rationale, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (score_id, session_id, topic_id, question_id, score, rationale, created_at.isoformat()),
            )

    def list_by_session(self, session_id: str) -> list[dict]:
        """Return all scores recorded for a session."""
        with self._db.connection() as conn:
            return conn.execute(
                "SELECT * FROM scores WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
