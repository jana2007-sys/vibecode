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


class CandidateAnalysis(BaseModelConfig):
    """Normalized candidate analysis consumed by the interview engine.

    Produced by ``CandidateAnalyzer.analyze`` and designed to be consumed by
    ``QuestionPlanner``. Every field is derived strictly from ``candidate.json``;
    when the source data has no information for a given dimension the field is
    left empty rather than invented.
    """

    candidate_id: Id
    profile: CandidateProfile = Field(description="The validated raw candidate profile.")
    completed_topics: list[str] = Field(
        default_factory=list,
        description="Missions/topics the candidate completed (from the learning journey).",
    )
    skipped_topics: list[str] = Field(
        default_factory=list,
        description="Missions/topics the candidate skipped. Empty when candidate.json has no such data.",
    )
    attempts: dict[str, int] = Field(
        default_factory=dict,
        description="Topic/subject -> number of attempts. Empty when candidate.json has no such data.",
    )
    learning_signals: list[str] = Field(
        default_factory=list,
        description="Derived learning preferences and context available in the profile.",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Candidate strengths derived only from the available profile data.",
    )
    areas_for_further_assessment: list[str] = Field(
        default_factory=list,
        description="Topics that may need further assessment, derived only from the available data.",
    )
