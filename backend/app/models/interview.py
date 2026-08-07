"""Interview API request/response contracts.

These models define the stable wire format between the frontend and backend.
Route handlers return placeholder payloads that already follow this shape, so the
frontend can be built before the business logic exists.
"""

from __future__ import annotations

from pydantic import Field

from app.models.common import BaseModelConfig, Id
from app.models.session import InterviewState
from app.models.message import MessageRole


class StartInterviewRequest(BaseModelConfig):
    """Body of POST /api/interview."""

    candidate_id: Id
    curriculum_id: Id


class StartInterviewResponse(BaseModelConfig):
    """Placeholder response for starting an interview.

    ``payload`` mirrors the future shape: the created session plus the first
    interviewer turn.
    """

    session_id: Id
    state: InterviewState
    message: str = Field(default="", description="First interviewer message.")
    payload: dict = Field(
        default_factory=dict,
        description="Reserved for full session + first step payload (future).",
    )


class AnswerRequest(BaseModelConfig):
    """Body of POST /api/interview/{session_id}/answer."""

    content: str = Field(min_length=1, max_length=20000, description="Candidate's answer text.")


class AnswerResponse(BaseModelConfig):
    """Placeholder response for an answered step."""

    session_id: Id
    state: InterviewState
    message: str = Field(default="", description="Interviewer's follow-up or next question.")
    role: MessageRole = MessageRole.INTERVIEWER
    payload: dict = Field(
        default_factory=dict,
        description="Reserved for next step / question payload (future).",
    )


class CompleteInterviewResponse(BaseModelConfig):
    """Placeholder response for ending an interview."""

    session_id: Id
    state: InterviewState = InterviewState.COMPLETED
    report_id: Id | None = None
    message: str = Field(default="", description="Closing message.")
    payload: dict = Field(
        default_factory=dict,
        description="Reserved for the full feedback report (future).",
    )
