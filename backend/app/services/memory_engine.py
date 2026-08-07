"""Conversation memory.

Keeps interviews context-aware: maintains the recent-turn window and (in the
future) compresses older turns into summaries so the LLM always has a bounded,
relevant context.

Collaborators: ConversationMemory, GeminiService.
"""

from __future__ import annotations

from app.memory.conversation_memory import ConversationMemory
from app.services.gemini_service import GeminiService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MemoryEngine:
    """Maintains and evolves per-session conversation context."""

    def __init__(
        self,
        conversation_memory: ConversationMemory,
        gemini_service: GeminiService | None = None,
    ) -> None:
        self._memory = conversation_memory
        self._gemini = gemini_service

    def record_turn(self, session_id: str, role: str, content: str) -> None:
        """Append one turn to the session's rolling context window."""
        self._memory.append(session_id, {"role": role, "content": content})

    def get_recent(self, session_id: str) -> list[dict]:
        """Return the recent turns for a session."""
        return self._memory.get(session_id)

    def get_summary(self, session_id: str) -> str | None:
        """Return the compressed summary of older turns, if any."""
        return self._memory.get_summary(session_id)

    def compress(self, session_id: str) -> None:
        """Summarize older turns when the window overflows.

        Placeholder: will call GeminiService to produce a running summary.
        """
        raise NotImplementedError("Conversation compression will be implemented later.")
