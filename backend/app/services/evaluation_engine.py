"""Candidate answer evaluation.

Scores a candidate's answer for a given question against the curriculum's
``expects`` concepts, producing a structured per-question evaluation and
persisting a 0-10 score through the existing ScoreRepository. Scoring is fully
deterministic and explainable; it is NOT a semantic (LLM) judgment. Gemini-based
evaluation will be layered on later via the stable ``GeminiService`` interface.

Deterministic scoring strategy
------------------------------

For a question with ``N`` expected concepts:

    score = 10.0 * coverage * length_factor

where

* ``coverage`` is the fraction of expected concepts the answer addresses
  (``matched / N``; exactly ``1.0`` when there is nothing to test).
* ``length_factor`` is ``min(1.0, unique_content_tokens / MIN_ANSWER_TOKENS)``,
  a penalty for extremely short answers so that naming a concept label without
  any elaboration cannot earn full marks. It is computed over *unique* tokens,
  so repeating the same word never inflates the score.

A concept is "matched" when every alphanumeric token of the concept appears in
the answer (case-insensitive). Multi-word concepts require all their tokens.
Empty or blank answers score ``0.0``. The same ``(answer, expects)`` input
always produces the same result.

Limitations: this is a lexical coverage heuristic, not comprehension. It cannot
judge whether an answer is *correct* or how well the candidate reasoned; it
rewards answers that mention the expected vocabulary and penalizes
impoverished/absent ones. A well-reasoned answer that avoids the expected
vocabulary will score low, and a fluent but shallow answer may score high.
Semantic correctness and reasoning signals are intentionally left out of the
deterministic evaluator (``AnswerEvaluation.reasoning`` is always ``None``).

Collaborators: GeminiService, ScoreRepository, MessageRepository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.models.common import new_uuid, utc_now
from app.services.gemini_service import GeminiService
from app.utils.logging import get_logger

logger = get_logger(__name__)

_TOKENS_PATTERN = re.compile(r"[a-z0-9]+")

#: Answers with fewer than this many *unique* content tokens are too brief to
#: earn full marks even when they name every expected concept.
MIN_ANSWER_TOKENS = 4

#: Completeness labels used by :class:`AnswerEvaluation`.
COMPLETENESS_EMPTY = "empty"
COMPLETENESS_UNSATISFACTORY = "unsatisfactory"
COMPLETENESS_PARTIAL = "partial"
COMPLETENESS_COMPLETE = "complete"


def _tokens(text: str) -> set[str]:
    """Return the normalized lowercase alphanumeric tokens of ``text``."""
    return set(_TOKENS_PATTERN.findall(text.lower()))


@dataclass(frozen=True)
class AnswerEvaluation:
    """Structured, deterministic evaluation of a single answer.

    Every concept field is grounded in the curriculum's ``expects`` data;
    nothing is invented by the evaluator.
    """

    score: float
    matched_concepts: list[str] = field(default_factory=list)
    missing_concepts: list[str] = field(default_factory=list)
    expected_concepts: int = 0
    coverage: float = 0.0
    completeness: str = COMPLETENESS_UNSATISFACTORY
    reasoning: str | None = None
    feedback: str = ""


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

    # --- Structured evaluation -----------------------------------------------

    def evaluate_answer_detail(
        self,
        session_id: str,
        topic_id: str,
        question_id: str,
        answer: str,
        expects: list[str] | None = None,
    ) -> AnswerEvaluation:
        """Evaluate an answer, persist its score, and return the full detail.

        Persists via the existing :class:`ScoreRepository` (the score and the
        human-readable feedback in ``rationale``), then returns the structured
        :class:`AnswerEvaluation` for downstream follow-up/feedback/prompts.
        """
        matched, missing = self.concept_coverage(answer, expects or [])
        evaluation = self._evaluate(matched, missing, answer)
        self._scores.create(
            score_id=new_uuid(),
            session_id=session_id,
            topic_id=topic_id,
            question_id=question_id,
            score=evaluation.score,
            rationale=evaluation.feedback,
            created_at=utc_now(),
        )
        logger.info(
            "Scored answer for %s/%s: %.2f (%d/%d concepts)",
            session_id,
            question_id,
            evaluation.score,
            len(matched),
            len(matched) + len(missing),
        )
        return evaluation

    def evaluate_answer(
        self,
        session_id: str,
        topic_id: str,
        question_id: str,
        answer: str,
        expects: list[str] | None = None,
    ) -> float:
        """Score a single answer on a 0-10 scale and persist the result.

        Convenience wrapper around :meth:`evaluate_answer_detail` that returns
        only the numeric score (kept for backward compatibility).
        """
        return self.evaluate_answer_detail(
            session_id, topic_id, question_id, answer, expects
        ).score

    def evaluate_topic(self, session_id: str, topic_id: str) -> float:
        """Aggregate per-question scores into a topic score.

        Averages every recorded score for the topic in the session; returns
        0.0 when the topic has no scores yet.
        """
        rows = [row for row in self._scores.list_by_session(session_id) if row["topic_id"] == topic_id]
        if not rows:
            return 0.0
        return round(sum(float(row["score"]) for row in rows) / len(rows), 2)

    # --- Deterministic scoring -----------------------------------------------

    @staticmethod
    def _evaluate(
        matched: list[str],
        missing: list[str],
        answer: str,
    ) -> AnswerEvaluation:
        """Derive the structured evaluation from concept coverage.

        See the module docstring for the exact scoring formula. This is a pure
        function of ``(answer, expects)``: the same input always yields the
        same evaluation.
        """
        total = len(matched) + len(missing)
        if total == 0:
            return AnswerEvaluation(
                score=10.0,
                matched_concepts=[],
                missing_concepts=[],
                expected_concepts=0,
                coverage=1.0,
                completeness=COMPLETENESS_COMPLETE,
                reasoning=None,
                feedback="No evaluable concepts; nothing to test.",
            )

        coverage = len(matched) / total
        unique_tokens = len(_tokens(answer))
        length_factor = min(1.0, unique_tokens / MIN_ANSWER_TOKENS)
        score = round(10.0 * coverage * length_factor, 2)
        completeness = EvaluationEngine._completeness(answer, coverage, length_factor)
        return AnswerEvaluation(
            score=score,
            matched_concepts=list(matched),
            missing_concepts=list(missing),
            expected_concepts=total,
            coverage=coverage,
            completeness=completeness,
            reasoning=None,
            feedback=EvaluationEngine._feedback(matched, missing, completeness),
        )

    @staticmethod
    def _completeness(answer: str, coverage: float, length_factor: float) -> str:
        """Label answer completeness from coverage and substance."""
        if not answer.strip():
            return COMPLETENESS_EMPTY
        if coverage >= 1.0 and length_factor >= 1.0:
            return COMPLETENESS_COMPLETE
        if coverage > 0.0:
            return COMPLETENESS_PARTIAL
        return COMPLETENESS_UNSATISFACTORY

    @staticmethod
    def _feedback(matched: list[str], missing: list[str], completeness: str) -> str:
        """Build candidate-facing feedback from the evaluation signals."""
        parts: list[str] = []
        if matched:
            parts.append("Covered: " + ", ".join(matched))
        if missing:
            parts.append("Missing: " + ", ".join(missing))
        if completeness == COMPLETENESS_EMPTY:
            parts.append("Answer is empty.")
        elif completeness == COMPLETENESS_COMPLETE:
            parts.append("Answer addresses every expected concept.")
        elif completeness == COMPLETENESS_PARTIAL:
            parts.append("Answer is only partial; elaborate on the expected concepts.")
        else:
            parts.append("Answer does not address the expected concepts.")
        return "; ".join(parts)
