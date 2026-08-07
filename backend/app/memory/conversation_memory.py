"""In-memory conversation store per session.

Future production design: swap this for Redis with a TTL so conversation context
survives process restarts and scales horizontally. The interface (``get`` /
``append`` / ``summarize``) is intentionally storage-agnostic.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)


class ConversationMemory:
    """Holds a rolling window of the most recent conversation turns per session.

    A bounded window keeps prompt context predictable; older turns are
    compressed by MemoryEngine into summaries (future).
    """

    MAX_TURNS = 20

    def __init__(self, max_turns: int = MAX_TURNS) -> None:
        self._store: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=max_turns)
        )
        self._summaries: dict[str, str] = {}

    def append(self, session_id: str, turn: dict[str, Any]) -> None:
        """Record a single turn (e.g. {'role': ..., 'content': ...})."""
        self._store[session_id].append(turn)

    def get(self, session_id: str) -> list[dict[str, Any]]:
        """Return the recent turns for a session in chronological order."""
        return list(self._store.get(session_id, []))

    def clear(self, session_id: str) -> None:
        """Drop all stored turns and summaries for a session."""
        self._store.pop(session_id, None)
        self._summaries.pop(session_id, None)

    # --- Summary support (future MemoryEngine) ---

    def set_summary(self, session_id: str, summary: str) -> None:
        """Cache a compressed summary of older conversation turns."""
        self._summaries[session_id] = summary

    def get_summary(self, session_id: str) -> str | None:
        """Return the cached summary for a session, if any."""
        return self._summaries.get(session_id)
