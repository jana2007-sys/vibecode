"""Candidate profile contracts.

The candidate knowledge source (``data/candidate.json``) is loaded and validated
into these models by ``CandidateAnalyzer``.
"""

from __future__ import annotations

from pydantic import Field

from app.models.common import BaseModelConfig, Id


class SkillLevel(BaseModelConfig):
    """A named skill together with the candidate's self-reported level."""

    name: str = Field(min_length=1)
    level: str = Field(
        default="unknown",
        description="e.g. beginner | intermediate | advanced | unknown",
    )


class LearningJourneyEntry(BaseModelConfig):
    """A step in the candidate's learning journey (course, project, book, ...)."""

    type: str = Field(description="e.g. course | project | book | practice")
    title: str = Field(min_length=1)
    description: str = Field(default="")


class CandidateProfile(BaseModelConfig):
    """Structured profile of a candidate."""

    id: Id
    name: str = Field(min_length=1)
    role: str = Field(default="", description="Target role, e.g. 'Backend Engineer'")
    years_of_experience: float = Field(default=0.0, ge=0)
    skills: list[SkillLevel] = Field(default_factory=list)
    learning_journey: list[LearningJourneyEntry] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    notes: str = Field(default="")
