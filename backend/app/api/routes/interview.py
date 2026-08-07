"""Interview endpoints — SKELETON ONLY.

These routes define the stable wire contract. Responses are placeholders that
mirror the future payload shape; no interview logic or Gemini calls happen here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter

from app.api.deps import SessionManagerDep
from app.models.interview import (
    AnswerRequest,
    AnswerResponse,
    CompleteInterviewResponse,
    StartInterviewRequest,
    StartInterviewResponse,
)
from app.models.session import InterviewState, SessionRead
from app.utils.errors import NotFoundError

router = APIRouter()


@router.post("/interview", response_model=StartInterviewResponse)
async def start_interview(
    body: StartInterviewRequest,
    session_manager: SessionManagerDep,
) -> StartInterviewResponse:
    """Create a new interview session.

    Placeholder: the session row is persisted; the introduction message and
    first question are hard-coded until InterviewEngine is implemented.
    """
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
