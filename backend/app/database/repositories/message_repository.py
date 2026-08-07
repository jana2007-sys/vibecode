"""Repository for the ``messages`` table."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.base import BaseRepository


class MessageRepository(BaseRepository):
    """Persistence for conversation transcripts."""

    table = "messages"

    def create(
        self,
        message_id: str,
        session_id: str,
        role: str,
        content: str,
        metadata: dict,
        created_at: datetime,
    ) -> None:
        """Append a single message to a session's transcript."""
        with self._db.connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, session_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, self._dumps(metadata), created_at.isoformat()),
            )

    def list_by_session(self, session_id: str) -> list[dict]:
        """Return the full transcript of a session, oldest first."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: dict) -> dict:
        """Convert raw row dict into the MessageRead shape."""
        row["metadata"] = self._loads(row["metadata"], {})
        return row
