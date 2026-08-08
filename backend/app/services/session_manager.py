"""Session lifecycle management.

Owns creating, loading and completing interview sessions, and keeps the
persisted state in sync with the state machine.

Collaborators: SessionRepository, StateMachine.
"""

from __future__ import annotations

from app.database.repositories.session_repository import SessionRepository
from app.memory.state_machine import StateMachine
from app.models.common import new_uuid, utc_now
from app.models.session import SessionCreate, SessionRead, InterviewState
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Coordinates session persistence and state transitions."""

    def __init__(
        self,
        session_repository: SessionRepository,
        state_machine: StateMachine | None = None,
    ) -> None:
        self._sessions = session_repository
        self._state_machine = state_machine or StateMachine()

    def create_session(self, data: SessionCreate, session_id: str | None = None) -> SessionRead:
        """Create and persist a new session in the START state.

        When ``session_id`` is given it is used as the primary key (allowing the
        interactive engine to honor client-supplied ids); otherwise one is
        generated.
        """
        session_id = session_id or new_uuid()
        now = utc_now()
        self._sessions.create(
            session_id=session_id,
            candidate_id=data.candidate_id,
            curriculum_id=data.curriculum_id,
            now=now,
        )
        logger.info("Created session %s for candidate %s", session_id, data.candidate_id)
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> SessionRead:
        """Load a session by id; raises NotFoundError when missing."""
        row = self._sessions.get_by_id(session_id)
        if row is None:
            from app.utils.errors import NotFoundError

            raise NotFoundError(f"Session {session_id} not found")
        row["context"] = self._sessions.loads_json(row.get("context"), {})
        return SessionRead(**row)

    def update_context(
        self,
        session_id: str,
        context: dict,
        *,
        topic_index: int | None = None,
    ) -> SessionRead:
        """Replace a session's context (and optionally its topic index)."""
        current = self.get_session(session_id)
        self._sessions.update_state(
            session_id,
            current.state,
            topic_index=topic_index,
            context=context,
        )
        return self.get_session(session_id)

    def advance(self, session_id: str, target: InterviewState) -> SessionRead:
        """Validate and persist a state transition for a session."""
        current = self.get_session(session_id)
        # SessionRead stores enum values as plain strings; normalize back to
        # the enum for state-machine validation.
        self._state_machine.transition(InterviewState(current.state), target)
        self._sessions.update_state(session_id, target.value)
        return self.get_session(session_id)

    def complete(self, session_id: str) -> SessionRead:
        """Move a session into the COMPLETED state, stamping its completion time."""
        current = self.get_session(session_id)
        self._state_machine.transition(InterviewState(current.state), InterviewState.COMPLETED)
        self._sessions.update_state(session_id, InterviewState.COMPLETED.value, completed_at=utc_now())
        return self.get_session(session_id)
