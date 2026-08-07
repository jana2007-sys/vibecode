"""Repository for the ``sessions`` table."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.database.repositories.base import BaseRepository


class SessionRepository(BaseRepository):
    """Persistence for interview sessions."""

    table = "sessions"

    def create(self, session_id: str, candidate_id: str, curriculum_id: str, now: datetime) -> None:
        """Insert a new session row in its initial state."""
        with self._db.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, candidate_id, curriculum_id, state, topic_index,
                                      context, created_at, updated_at)
                VALUES (?, ?, ?, 'START', 0, '{}', ?, ?)
                """,
                (session_id, candidate_id, curriculum_id, now.isoformat(), now.isoformat()),
            )

    def update_state(
        self,
        session_id: str,
        state: str,
        *,
        topic_index: int | None = None,
        context: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
        now: datetime | None = None,
    ) -> None:
        """Update mutable session fields for a given session."""
        if now is None:
            from app.models.common import utc_now

            now = utc_now()
        context_raw = self._dumps(context) if context is not None else None
        with self._db.connection() as conn:
            conn.execute(
                """
                UPDATE sessions
                   SET state = ?,
                       topic_index = COALESCE(?, topic_index),
                       context = COALESCE(?, context),
                       completed_at = COALESCE(?, completed_at),
                       updated_at = ?
                 WHERE id = ?
                """,
                (state, topic_index, context_raw, completed_at.isoformat() if completed_at else None, now.isoformat(), session_id),
            )

    def list_all(self) -> list[dict]:
        """Return all sessions ordered by most recently updated."""
        with self._db.connection() as conn:
            return conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
