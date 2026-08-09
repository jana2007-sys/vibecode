"""Candidate profile contracts.

The candidate knowledge source (``data/candidate.json``) is loaded and validated
into these models by ``CandidateAnalyzer``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

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
    experience_level: str = Field(
        default="mid",
        description="junior | mid | senior. Only honored for custom profiles (id prefix 'custom-').",
    )
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


class CandidateCreate(BaseModelConfig):
    """Payload to create/persist a candidate profile.

    Deliberately extends the wire ``CandidateProfile`` with ``email`` and
    ``strengths``. ``CandidateProfile`` (the interview wire contract) is left
    untouched so ``POST /api/interview`` stays backwards compatible.
    """

    name: str = Field(min_length=1)
    email: str = Field(
        min_length=3,
        description="Contact email. Must contain a single '@'.",
    )
    role: str = Field(default="", description="Target role, e.g. 'Backend Engineer'")
    years_of_experience: float = Field(default=0.0, ge=0)
    experience_level: str = Field(default="mid", description="junior | mid | senior")
    skills: list[SkillLevel] = Field(default_factory=list)
    learning_journey: list[LearningJourneyEntry] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    notes: str = Field(default="")

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        email = value.strip()
        if email.count("@") != 1:
            raise ValueError("Email must contain exactly one '@'")
        local, domain = email.split("@")
        if not local or not domain or "." not in domain:
            raise ValueError("Email must have a non-empty local part and a valid domain")
        return email

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Name must not be empty")
        return name


class CandidateRead(BaseModelConfig):
    """A persisted candidate profile row."""

    id: Id
    name: str
    email: str | None = None
    role: str = Field(default="")
    years_of_experience: float = Field(default=0.0, ge=0)
    experience_level: str = Field(default="mid")
    skills: list[SkillLevel] = Field(default_factory=list)
    learning_journey: list[LearningJourneyEntry] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    notes: str = Field(default="")
    is_custom: bool = Field(
        default=False,
        description="True for profiles added via the API; False for the predefined seeded profiles.",
    )
    created_at: datetime
    updated_at: datetime


class CandidateList(BaseModelConfig):
    """Paginated or flat list of persisted candidates."""

    items: list[CandidateRead]
    total: int


class DeleteResult(BaseModelConfig):
    """Result of a candidate / history deletion."""

    deleted: bool = Field(default=True)
    deleted_sessions: int = Field(default=0, ge=0)


def is_custom_profile(candidate_id: str) -> bool:
    """Return True for profiles added via the API (ids prefixed 'custom-')."""
    return candidate_id.startswith("custom-")
