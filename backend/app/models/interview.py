"""Interview API request/response contracts.

These models define the stable wire format between the frontend and backend.
Route handlers return placeholder payloads that already follow this shape, so the
frontend can be built before the business logic exists.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, model_validator

from app.models.candidate import CandidateProfile
from app.models.common import BaseModelConfig, Id
from app.models.session import InterviewState
from app.models.message import MessageRole


class InterviewTurnRequest(BaseModelConfig):
    """Body of POST /api/interview (the interactive interview contract).

    The first call carries a ``candidate`` to start the interview; every
    subsequent call carries a ``message`` (the candidate's answer). Exactly one
    of the two must be present.
    """

    session_id: Id = Field(alias="sessionId")
    candidate: CandidateProfile | None = None
    message: str | None = Field(default=None, min_length=1, max_length=20000)

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        use_enum_values=True,
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _require_exactly_one_input(self) -> "InterviewTurnRequest":
        has_candidate = self.candidate is not None
        has_message = self.message is not None
        if has_candidate == has_message:
            raise ValueError(
                "Provide exactly one of 'candidate' (to start) or 'message' (to answer)"
            )
        return self


class InterviewFeedback(BaseModelConfig):
    """Structured feedback returned when an interview completes."""

    summary: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next: list[str] = Field(default_factory=list)


class InterviewTurnResponse(BaseModelConfig):
    """Response to every POST /api/interview call."""

    reply: str = Field(min_length=1, description="Interviewer's message.")
    done: bool = Field(default=False, description="True when the interview is complete.")
    feedback: InterviewFeedback | None = Field(
        default=None,
        description="Present only when ``done`` is True.",
    )


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
