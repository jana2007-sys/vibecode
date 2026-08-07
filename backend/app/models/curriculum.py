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
