"""Interview endpoints.

The primary interactive contract is a single ``POST /api/interview`` endpoint:
the first call carries a ``candidate`` to start the interview and every
subsequent call carries a ``message`` (the candidate's answer). The legacy
start/answer/complete routes remain for backwards compatibility with the
earlier skeleton contract.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import InterviewEngineDep, SessionManagerDep
from app.models.interview import (
    AnswerRequest,
    AnswerResponse,
    CompleteInterviewResponse,
    InterviewTurnRequest,
    InterviewTurnResponse,
    StartInterviewRequest,
    StartInterviewResponse,
)
from app.models.session import InterviewState, SessionRead
from app.utils.errors import NotFoundError

router = APIRouter()


@router.post("/interview", response_model=InterviewTurnResponse)
async def interview_turn(
    body: InterviewTurnRequest,
    interview_engine: InterviewEngineDep,
) -> InterviewTurnResponse:
    """Run one interactive interview turn.

    With ``candidate`` set this starts the interview; with ``message`` set it
    processes the candidate's answer and returns the next interviewer turn.
    """
    if body.candidate is not None:
        return interview_engine.start(body.session_id, body.candidate)
    return interview_engine.handle_answer(body.session_id, body.message)


@router.post("/interview/legacy", response_model=StartInterviewResponse)
async def start_interview(
    body: StartInterviewRequest,
    session_manager: SessionManagerDep,
) -> StartInterviewResponse:
    """Create a new interview session (legacy skeleton contract)."""
    session = session_manager.create_session(body)
    return StartInterviewResponse(
        session_id=session.id,
        state=session.state,
        message="Welcome to your InterVue AI interview. We'll begin shortly.",
        payload={
            "candidate_id": body.candidate_id,
            "curriculum_id": body.curriculum_id,
            "hint": "Interview orchestration is not implemented yet.",
        },
    )


@router.post("/interview/{session_id}/answer", response_model=AnswerResponse)
async def answer_interview(
    session_id: str,
    body: AnswerRequest,
    session_manager: SessionManagerDep,
) -> AnswerResponse:
    """Submit a candidate answer.

    Placeholder: verifies the session exists and returns a canned follow-up.
    """
    session = session_manager.get_session(session_id)
    if session.state == InterviewState.COMPLETED:
        raise NotFoundError(f"Session {session_id} is already completed")
    return AnswerResponse(
        session_id=session_id,
        state=session.state,
        message="Thanks — a tailored follow-up will appear once interview logic is enabled.",
        payload={"received_answer_length": len(body.content)},
    )


@router.post("/interview/{session_id}/complete", response_model=CompleteInterviewResponse)
async def complete_interview(
    session_id: str,
    session_manager: SessionManagerDep,
) -> CompleteInterviewResponse:
    """End an interview and (in the future) return its report.

    Placeholder: marks the session complete; the report stays empty until
    FeedbackGenerator is implemented.
    """
    session = session_manager.complete(session_id)
    return CompleteInterviewResponse(
        session_id=session_id,
        state=session.state,
        report_id=None,
        message="Interview session complete. Reports are not generated yet.",
        payload={"completed_at": session.completed_at.isoformat() if session.completed_at else None},
    )


@router.get("/interview/{session_id}", response_model=SessionRead)
async def get_interview_session(
    session_id: str,
    session_manager: SessionManagerDep,
) -> SessionRead:
    """Fetch the current state of an interview session."""
    return session_manager.get_session(session_id)
