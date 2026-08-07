"""Session & report query endpoints — SKELETON ONLY."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import FeedbackRepositoryDep, SessionManagerDep, SessionRepositoryDep
from app.models.feedback import FeedbackRead
from app.models.session import SessionList, SessionRead

router = APIRouter()


@router.get("/sessions", response_model=SessionList)
async def list_sessions(
    session_repository: SessionRepositoryDep,
) -> SessionList:
    """List all interview sessions, newest first."""
    rows = session_repository.list_all()
    hydrated = []
    for row in rows:
        row["context"] = session_repository.loads_json(row.get("context"), {})
        hydrated.append(SessionRead(**row))
    return SessionList(items=hydrated, total=len(hydrated))


@router.get("/sessions/{session_id}/report", response_model=FeedbackRead)
async def get_session_report(
    session_id: str,
    session_manager: SessionManagerDep,
    feedback_repository: FeedbackRepositoryDep,
) -> FeedbackRead:
    """Retrieve the final report for a completed session.

    Placeholder: returns an empty report until FeedbackGenerator is wired in.
    """
    # Verify the session exists (raises 404 otherwise).
    session_manager.get_session(session_id)
    row = feedback_repository.get_by_session(session_id)
    if row is None:
        from app.utils.errors import NotFoundError

        raise NotFoundError(f"No feedback report for session {session_id}")
    return FeedbackRead(**row)
