"""Archived enrollment contracts.

These models describe the rows stored in the private database: an enrolled
candidate snapshot plus the full report of every interview they completed.
They are used by the archive layer and tests; they are intentionally NOT part
of the public API contract.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.common import BaseModelConfig, Id


class EnrolledCandidate(BaseModelConfig):
    """A snapshot of a candidate profile stored in the private database."""

    id: Id
    name: str
    email: str | None = None
    role: str = Field(default="")
    years_of_experience: float = Field(default=0.0, ge=0)
    experience_level: str = Field(default="mid")
    skills: list[dict] = Field(default_factory=list)
    learning_journey: list[dict] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    notes: str = Field(default="")
    enrolled_at: datetime


class EnrolledReport(BaseModelConfig):
    """A full report archived in the private database."""

    session_id: Id
    candidate_id: Id
    report: dict = Field(
        description="The serialized ReportRead payload for the completed session."
    )
    completed_at: datetime


class EnrollmentRead(BaseModelConfig):
    """One archived enrollment: the candidate snapshot + their reports."""

    candidate: EnrolledCandidate
    reports: list[EnrolledReport] = Field(default_factory=list)
