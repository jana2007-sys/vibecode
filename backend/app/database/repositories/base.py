"""Generic repository base.

Repositories are the only code allowed to touch the SQL layer. Business logic
lives in services; API contracts are produced by models.
"""

from __future__ import annotations

import json
from typing import Any

from app.database.connection import Database


class BaseRepository:
    """Common helpers for all repositories."""

    table: str = ""

    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def dumps_json(value: Any) -> str:
        """Serialize a Python value to a JSON string for TEXT storage."""
        return json.dumps(value)

    @staticmethod
    def loads_json(raw: str | None, default: Any = None) -> Any:
        """Parse a JSON string back into a Python value."""
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default

    # Backwards-compatible private aliases used by existing call sites.
    _dumps = dumps_json
    _loads = loads_json

    def get_by_id(self, record_id: str) -> dict | None:
        """Fetch a single row by primary key, or None."""
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table} WHERE id = ?",
                (record_id,),
            ).fetchone()
        return row

    def delete_by_id(self, record_id: str) -> bool:
        """Delete a row by primary key; returns True when a row was removed."""
        with self._db.connection() as conn:
            cursor = conn.execute(
                f"DELETE FROM {self.table} WHERE id = ?",
                (record_id,),
            )
        return cursor.rowcount > 0
