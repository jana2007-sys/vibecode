"""Curriculum contracts.

The curriculum knowledge source (``data/curriculum.json``) defines the ordered
topics and question templates the interview engine will walk through.
"""

from __future__ import annotations

from pydantic import Field

from app.models.common import BaseModelConfig, Id


class QuestionTemplate(BaseModelConfig):
    """A reusable question template within a topic."""

    id: Id
    text: str = Field(min_length=1, description="Question text or template with {placeholders}.")
    difficulty: str = Field(default="medium", description="easy | medium | hard")
    expects: list[str] = Field(
        default_factory=list,
        description="Keywords / concepts an ideal answer should mention (future evaluation).",
    )


class Topic(BaseModelConfig):
    """A curriculum topic with its ordered questions."""

    id: Id
    title: str = Field(min_length=1)
    description: str = Field(default="")
    questions: list[QuestionTemplate] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0.0, description="Relative importance for scoring.")


class Curriculum(BaseModelConfig):
    """The full ordered learning path used as the interview roadmap."""

    id: Id
    title: str = Field(min_length=1)
    description: str = Field(default="")
    version: str = Field(default="1.0.0")
    topics: list[Topic] = Field(default_factory=list)


class PlannedQuestion(BaseModelConfig):
    """A single grounded interview question within a plan.

    Produced by ``QuestionPlanner``. Every question is grounded in a curriculum
    ``QuestionTemplate`` (``text`` and ``expects`` are taken verbatim); dynamic
    follow-ups are never generated here.
    """

    sequence: int = Field(ge=1, description="1-based position within the interview.")
    topic_id: Id
    curriculum_question_id: Id
    text: str = Field(min_length=1, description="Question text, verbatim from the curriculum.")
    difficulty: str = Field(description="Difficulty label, preserved from the curriculum.")
    expects: list[str] = Field(
        default_factory=list,
        description="Concepts an ideal answer should mention (from the curriculum).",
    )
    question_type: str = Field(
        default="conceptual",
        description="conceptual | explanation | comparison | troubleshooting | scenario | architecture",
    )
    follow_up_allowed: bool = Field(
        default=True,
        description="Whether the InterviewEngine may ask a dynamic follow-up after this question.",
    )


class InterviewPlan(BaseModelConfig):
    """A deterministic, personalized interview plan.

    Produced by ``QuestionPlanner``. Guarantees a minimum of 8 grounded
    questions covering at least 4 distinct curriculum topics.
    """

    candidate_id: Id
    curriculum_id: Id
    total_questions: int = Field(ge=8, description="Number of planned questions (minimum 8).")
    topics_covered: list[str] = Field(
        description="Distinct topic ids covered, in first-appearance order."
    )
    questions: list[PlannedQuestion] = Field(min_length=8)
