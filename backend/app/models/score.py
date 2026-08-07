"""Evaluation score contracts.

Scores capture the candidate's performance per question and per topic so that
the FeedbackGenerator can assemble a structured report.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.common import BaseModelConfig, Id


class ScoreRead(BaseModelConfig):
    """A persisted evaluation score record."""

    id: Id
    session_id: Id
    topic_id: str = Field(default="")
    question_id: str = Field(default="")
    score: float = Field(ge=0.0, le=10.0, description="Normalized 0-10 score.")
    rationale: str = Field(default="", description="Short justification (future LLM output).")
    created_at: datetime


class ScoreCreate(BaseModelConfig):
    """Payload to persist a new evaluation score."""

    session_id: Id
    topic_id: str = Field(default="")
    question_id: str = Field(default="")
    score: float = Field(ge=0.0, le=10.0)
    rationale: str = Field(default="")
