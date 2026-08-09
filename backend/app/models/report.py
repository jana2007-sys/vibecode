"""Interview history and report response contracts.

A "report" is the full persisted artifact for one completed interview: the
session, the candidate, the structured feedback, and the transcript. History is
the per-candidate list of interviews.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.common import BaseModelConfig, Id
from app.models.feedback import FeedbackRead
from app.models.session import InterviewState


class ReportMessage(BaseModelConfig):
    """One transcript entry embedded in a report."""

    id: Id
    role: str = Field(description="system | interviewer | candidate")
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class ReportCandidate(BaseModelConfig):
    """Candidate summary embedded in a report."""

    id: Id
    name: str
    role: str = Field(default="")
    email: str | None = None
    strengths: list[str] = Field(default_factory=list)


class AnswerReview(BaseModelConfig):
    """Per-question answer verification embedded in a report.

    Pairs a graded question with the candidate's answer and the score the
    evaluator recorded for it.
    """

    question_id: str
    topic_id: str = Field(default="")
    topic_title: str = Field(default="")
    question: str
    answer: str = Field(default="")
    score: float = Field(ge=0.0, le=10.0)
    rationale: str = Field(default="")
    verdict: str = Field(
        description="'Very good' when score > 8, otherwise 'Needs improvement'."
    )


class ReportRead(BaseModelConfig):
    """The complete report for a single interview session."""

    session_id: Id
    candidate: ReportCandidate
    feedback: FeedbackRead
    completed_at: datetime | None = None
    messages: list[ReportMessage] = Field(default_factory=list)
    answer_reviews: list[AnswerReview] = Field(default_factory=list)


class InterviewHistoryItem(BaseModelConfig):
    """One row in a candidate's interview history."""

    session_id: Id
    state: InterviewState
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    overall_score: float | None = Field(
        default=None,
        description="Present when the session has a persisted feedback report.",
    )
    summary: str = Field(default="")


class InterviewHistory(BaseModelConfig):
    """The interview history for a single candidate."""

    candidate_id: Id
    items: list[InterviewHistoryItem]
    total: int
