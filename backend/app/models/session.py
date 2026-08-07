"""Interview session contracts.

A ``Session`` represents one complete interview run for a candidate against a
specific curriculum.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.common import BaseModelConfig, Id


class InterviewState(StrEnum):
    """The lifecycle states of an interview session.

    Mirrors the canonical state machine in ``app/memory/state_machine.py``.
    """

    START = "START"
    INTRODUCTION = "INTRODUCTION"
    QUESTION = "QUESTION"
    FOLLOW_UP = "FOLLOW_UP"
    NEXT_TOPIC = "NEXT_TOPIC"
    SUMMARY = "SUMMARY"
    COMPLETED = "COMPLETED"


class SessionCreate(BaseModelConfig):
    """Payload required to open a new interview session."""

    candidate_id: Id
    curriculum_id: Id


class SessionRead(BaseModelConfig):
    """Full representation of an interview session."""

    id: Id
    candidate_id: Id
    curriculum_id: Id
    state: InterviewState
    topic_index: int = Field(default=0, description="Index of the active topic in the curriculum.")
    context: dict = Field(
        default_factory=dict,
        description="Arbitrary session context (current topic, follow-up depth, ...).",
    )
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class SessionList(BaseModelConfig):
    """Paginated or flat list of sessions."""

    items: list[SessionRead]
    total: int
