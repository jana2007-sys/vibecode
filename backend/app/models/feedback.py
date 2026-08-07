"""Structured interview feedback / report contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.common import BaseModelConfig, Id


class TopicSummary(BaseModelConfig):
    """Per-topic feedback block."""

    topic_id: str
    title: str = Field(default="")
    average_score: float = Field(ge=0.0, le=10.0)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class FeedbackRead(BaseModelConfig):
    """The final interview report."""

    id: Id
    session_id: Id
    overall_score: float = Field(ge=0.0, le=10.0)
    summary: str = Field(default="")
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    topics: list[TopicSummary] = Field(default_factory=list)
    created_at: datetime
