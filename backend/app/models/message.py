"""Conversation message contracts.

Messages form the full transcript of an interview session and are the source of
truth for memory, evaluation and feedback.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.common import BaseModelConfig, Id


class MessageRole(StrEnum):
    """Who produced the message."""

    SYSTEM = "system"
    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


class MessageCreate(BaseModelConfig):
    """Payload to append a message to a session transcript."""

    session_id: Id
    role: MessageRole
    content: str = Field(min_length=1, max_length=20000)
    metadata: dict = Field(default_factory=dict, description="Optional structured data (e.g. question_id).")


class MessageRead(BaseModelConfig):
    """Persisted message record."""

    id: Id
    session_id: Id
    role: MessageRole
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
