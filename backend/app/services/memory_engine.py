"""Session memory.

The hardened memory layer gives the interview system a reliable, session-scoped
view of everything relevant from the current interview. The durable source of
truth is the existing SQLite session architecture:

* ``sessions.context`` (JSON) — candidate analysis, plan, current question,
  primary/follow-up counts, covered topics, asked questions, answers and
  evaluation summaries, all written atomically by the InterviewEngine.
* ``messages`` — the full chronological transcript with per-message metadata
  (kind, question_id, topic_id).
* ``scores`` — persisted per-question / per-topic evaluation scores.
* ``feedback`` — the final report produced when the interview completes.

``MemoryEngine`` now also maintains the live in-memory rolling window
(``record_turn`` / ``get_recent``) for recent-turn context, and exposes durable
retrieval helpers (``get_session_memory``, ``get_conversation_history``,
``get_previous_answers``, ``get_evaluations``, ``get_covered_topics``,
``get_current_question``, ``get_missing_concepts``,
``get_interview_summary_context``).

Isolation: every retrieval is scoped by ``session_id`` (SQL ``WHERE`` filters
plus per-session in-memory keys). A missing session raises the existing
``NotFoundError``. Completed sessions stay readable; they cannot be mutated
through normal interview continuation because the engine rejects answers on
completed sessions before writing anything.

Collaborators: ConversationMemory, SessionRepository, MessageRepository,
ScoreRepository, FeedbackRepository, GeminiService (unused; kept for the
future conversation compression).
"""

from __future__ import annotations

from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.memory.conversation_memory import ConversationMemory
from app.services.gemini_service import GeminiService
from app.utils.errors import NotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MemoryEngine:
    """Maintains and retrieves per-session interview memory.

    The rolling conversation window is in-memory (bounded by
    :class:`ConversationMemory`); everything else is read from the existing
    database repositories, so memory survives a fresh service/repository
    instance.
    """

    def __init__(
        self,
        conversation_memory: ConversationMemory,
        gemini_service: GeminiService | None = None,
        *,
        session_repository: SessionRepository | None = None,
        message_repository: MessageRepository | None = None,
        score_repository: ScoreRepository | None = None,
        feedback_repository: FeedbackRepository | None = None,
    ) -> None:
        self._memory = conversation_memory
        self._gemini = gemini_service
        self._sessions = session_repository
        self._messages = message_repository
        self._scores = score_repository
        self._feedback = feedback_repository

    # --- Live rolling window (in-memory) -------------------------------------

    def record_turn(self, session_id: str, role: str, content: str) -> None:
        """Append one turn to the session's rolling context window."""
        self._memory.append(session_id, {"role": role, "content": content})

    def get_recent(self, session_id: str) -> list[dict]:
        """Return the recent turns for a session (live window only)."""
        return self._memory.get(session_id)

    def get_summary(self, session_id: str) -> str | None:
        """Return the compressed summary of older turns, if any."""
        return self._memory.get_summary(session_id)

    def compress(self, session_id: str) -> None:
        """Summarize older turns when the window overflows.

        Placeholder: will call GeminiService to produce a running summary.
        """
        raise NotImplementedError("Conversation compression will be implemented later.")

    # --- Durable session memory ----------------------------------------------

    def get_session_memory(self, session_id: str) -> dict:
        """Return a structured, session-scoped snapshot of interview memory.

        Combines the persisted session row, its context (candidate analysis,
        plan, counts, questions/answers/evaluations, covered topics) and the
        final feedback report when one exists. Raises ``NotFoundError`` for an
        unknown session.
        """
        row = self._load_session_row(session_id)
        context = row.get("context", {})
        return {
            "session_id": row["id"],
            "candidate_id": row["candidate_id"],
            "curriculum_id": row["curriculum_id"],
            "state": row["state"],
            "topic_index": row["topic_index"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
            "phase": context.get("phase", "question"),
            "primary_index": context.get("primary_index", 0),
            "primary_question_count": context.get("primary_question_count", 0),
            "follow_up_count": context.get("follow_up_count", 0),
            "primary_answered": context.get("primary_answered", 0),
            "plan": context.get("plan", {}),
            "analysis": context.get("analysis", {}),
            "current_question": context.get("current"),
            "pending_follow_up": context.get("pending_follow_up"),
            "asked_questions": context.get("asked_questions", []),
            "answers": context.get("answers", []),
            "evaluations": context.get("evaluations", []),
            "topics_covered": context.get("topics_covered", []),
            "follow_ups": context.get("follow_ups", []),
            "feedback": self._feedback.get_by_session(session_id),
        }

    def get_conversation_history(self, session_id: str) -> list[dict]:
        """Return the full persisted transcript, oldest first.

        Messages carry ``role``, ``content``, ``metadata`` (kind,
        question_id, topic_id) and ``created_at``. The ``kind`` metadata
        distinguishes ``question``, ``answer`` and ``follow_up`` messages.
        """
        self._require_session(session_id)
        return self._messages.list_by_session(session_id)

    def get_previous_answers(self, session_id: str) -> list[dict]:
        """Return candidate answers in the order they were given."""
        return self.get_session_memory(session_id)["answers"]

    def get_asked_questions(self, session_id: str) -> list[dict]:
        """Return every question asked so far, in ask order."""
        return self.get_session_memory(session_id)["asked_questions"]

    def get_evaluations(self, session_id: str) -> list[dict]:
        """Return evaluation summaries in evaluation order.

        Each entry carries ``question_id``, ``topic_id``, ``kind``
        (``primary`` / ``follow_up``), ``score`` and ``missing`` concepts.
        """
        return self.get_session_memory(session_id)["evaluations"]

    def get_covered_topics(self, session_id: str) -> list[str]:
        """Return topic ids covered so far, in first-appearance order."""
        return self.get_session_memory(session_id)["topics_covered"]

    def get_current_question(self, session_id: str) -> dict | None:
        """Return the active/unanswered question, or ``None``.

        Returns ``None`` once the interview has finished (SUMMARY/COMPLETED),
        since there is no longer an unanswered question to retrieve.
        """
        memory = self.get_session_memory(session_id)
        if memory["state"] in {"SUMMARY", "COMPLETED"}:
            return None
        return memory["current_question"]

    def get_missing_concepts(self, session_id: str) -> list[str]:
        """Return distinct curriculum concepts still missing, in order.

        Flattens the ``missing`` lists of every recorded evaluation, preserving
        first-appearance order and de-duplicating.
        """
        missing: list[str] = []
        for evaluation in self.get_session_memory(session_id)["evaluations"]:
            for concept in evaluation.get("missing", []):
                if concept not in missing:
                    missing.append(concept)
        return missing

    def get_interview_summary_context(self, session_id: str) -> dict:
        """Return a compact, prompt-friendly summary of the interview memory."""
        memory = self.get_session_memory(session_id)
        current = memory["current_question"] or {}
        profile = memory["analysis"].get("profile", {})
        return {
            "session_id": session_id,
            "candidate_id": memory["candidate_id"],
            "candidate_name": profile.get("name", ""),
            "candidate_role": profile.get("role", ""),
            "curriculum_id": memory["curriculum_id"],
            "state": memory["state"],
            "phase": memory["phase"],
            "total_questions": memory["plan"].get("total_questions", 0),
            "primary_question_count": memory["primary_question_count"],
            "follow_up_count": memory["follow_up_count"],
            "current_question": {
                "question_id": current.get("curriculum_question_id", ""),
                "topic_id": current.get("topic_id", ""),
                "difficulty": current.get("difficulty", ""),
                "text": current.get("text", ""),
            },
            "topics_covered": memory["topics_covered"],
            "missing_concepts": self.get_missing_concepts(session_id),
            "feedback": memory["feedback"],
        }

    # --- Internals -----------------------------------------------------------

    def _require_wired(self) -> None:
        """Guard retrieval methods that need the persistence repositories."""
        if None in (self._sessions, self._messages, self._scores, self._feedback):
            raise ValueError(
                "MemoryEngine is not wired for durable retrieval; provide "
                "session/message/score/feedback repository dependencies"
            )

    def _require_session(self, session_id: str) -> dict:
        """Load the raw session row, raising NotFoundError when absent."""
        self._require_wired()
        row = self._sessions.get_by_id(session_id)
        if row is None:
            raise NotFoundError(f"Session {session_id} not found")
        return row

    def _load_session_row(self, session_id: str) -> dict:
        """Load a session row with its context parsed from JSON."""
        row = self._require_session(session_id)
        row["context"] = self._sessions.loads_json(row.get("context"), {})
        return row
