"""Candidate answer evaluation.

Scores a candidate's answer for a given question, producing per-question and
per-topic scores. Scoring is currently deterministic (keyword coverage of the
question's ``expects`` concepts); it will be delegated to the LLM
(GeminiService) once enabled. This class owns the orchestration and persistence.

Collaborators: GeminiService, ScoreRepository, MessageRepository.
"""

from __future__ import annotations

import re

from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.models.common import new_uuid, utc_now
from app.services.gemini_service import GeminiService
from app.utils.logging import get_logger

logger = get_logger(__name__)

_TOKENS_PATTERN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Return the normalized lowercase alphanumeric tokens of ``text``."""
    return set(_TOKENS_PATTERN.findall(text.lower()))


class EvaluationEngine:
    """Evaluates candidate answers and persists scores."""

    def __init__(
        self,
        gemini_service: GeminiService,
        score_repository: ScoreRepository,
        message_repository: MessageRepository,
    ) -> None:
        self._gemini = gemini_service
        self._scores = score_repository
        self._messages = message_repository

    # --- Deterministic concept coverage --------------------------------------

    def concept_coverage(self, answer: str, expects: list[str]) -> tuple[list[str], list[str]]:
        """Return ``(covered_concepts, missing_concepts)`` for an answer.

        A concept counts as covered when every token of the concept appears in
        the answer (case-insensitive). Empty/blank concepts are ignored so they
        never skew the score or trigger a follow-up.
        """
        answer_tokens = _tokens(answer)
        covered: list[str] = []
        missing: list[str] = []
        for concept in expects or []:
            concept_tokens = _tokens(concept)
            if not concept_tokens:
                continue
            if concept_tokens <= answer_tokens:
                covered.append(concept)
            else:
                missing.append(concept)
        return covered, missing

    def evaluate_answer(
        self,
        session_id: str,
        topic_id: str,
        question_id: str,
        answer: str,
        expects: list[str] | None = None,
    ) -> float:
        """Score a single answer on a 0-10 scale and persist the result.

        The score is the share of the question's ``expects`` concepts the
        answer covers, scaled to 0-10. A question with no evaluable concepts
        scores a perfect 10.0 (nothing was missing to test).
        """
        covered, missing = self.concept_coverage(answer, expects or [])
        total = len(covered) + len(missing)
        score = round(10.0 * len(covered) / total, 2) if total else 10.0
        rationale = self._rationale(covered, missing)
        self._scores.create(
            score_id=new_uuid(),
            session_id=session_id,
            topic_id=topic_id,
            question_id=question_id,
            score=score,
            rationale=rationale,
            created_at=utc_now(),
        )
        logger.info(
            "Scored answer for %s/%s: %.2f (%d/%d concepts)",
            session_id,
            question_id,
            score,
            len(covered),
            total,
        )
        return score

    def evaluate_topic(self, session_id: str, topic_id: str) -> float:
        """Aggregate per-question scores into a topic score.

        Averages every recorded score for the topic in the session; returns
        0.0 when the topic has no scores yet.
        """
        rows = [row for row in self._scores.list_by_session(session_id) if row["topic_id"] == topic_id]
        if not rows:
            return 0.0
        return round(sum(float(row["score"]) for row in rows) / len(rows), 2)

    # --- Helpers -------------------------------------------------------------

    @staticmethod
    def _rationale(covered: list[str], missing: list[str]) -> str:
        """Describe which concepts the answer covered and which it missed."""
        parts: list[str] = []
        if covered:
            parts.append("Covered: " + ", ".join(covered))
        if missing:
            parts.append("Missing: " + ", ".join(missing))
        return "; ".join(parts) or "No evaluable concepts."
