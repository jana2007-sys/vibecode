"""Adaptive follow-up decisions for the interactive interview.

Wraps PromptBuilder + GeminiService to decide whether ONE grounded follow-up is
appropriate for a primary answer and, when appropriate, to produce that single
follow-up question. The decision is grounded in the curriculum topic, the
current question and its expected concepts, the candidate's actual answer, the
deterministic evaluation, and the recent conversation.

Reliability: every Gemini failure (disabled, unavailable, LLM error, malformed
JSON, unknown target concept, unexpected exception) degrades gracefully to the
deterministic follow-up heuristic, so Gemini can never terminate an interview.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.gemini_service import GeminiService
from app.services.prompt_builder import FOLLOW_UP_SCHEMA, PromptBuilder
from app.utils.errors import ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

AI_SOURCE = "ai"
DETERMINISTIC_SOURCE = "deterministic"


def match_expected_concept(target_concept: str, expects: list[str]) -> str | None:
    """Return the curriculum-spelled concept matching ``target_concept``.

    ``None`` when no expected concept matches, so callers can reject (and fall
    back) rather than let the LLM invent facts. Matching is case-insensitive.
    """
    if not target_concept:
        return None
    for concept in expects or []:
        if concept.strip().lower() == target_concept.strip().lower():
            return concept
    return None


@dataclass(frozen=True)
class FollowUpDecision:
    """A single, grounded follow-up decision for one primary answer."""

    should_follow_up: bool
    reason: str
    question: str
    target_concept: str | None
    source: str


class FollowUpAdvisor:
    """Produces at most one follow-up decision per primary answer."""

    def __init__(
        self,
        prompt_builder: PromptBuilder,
        gemini_service: GeminiService,
    ) -> None:
        self._builder = prompt_builder
        self._gemini = gemini_service

    def decide(
        self,
        *,
        session_id: str,
        topic: dict,
        question: dict,
        answer: str,
        evaluation: dict,
        conversation_context: list[dict],
    ) -> FollowUpDecision:
        """Return the follow-up decision, always safe to consume.

        Uses Gemini when enabled and falls back to the deterministic
        concept-coverage heuristic on any failure.
        """
        fallback = self._deterministic_fallback(question, evaluation)
        if not self._gemini.enabled:
            logger.info(
                "Gemini follow-up disabled; using deterministic decision for %s/%s",
                session_id,
                question.get("curriculum_question_id"),
            )
            return fallback

        try:
            prompt = self._builder.build_follow_up_prompt(
                session_id=session_id,
                topic=topic,
                question=question,
                answer=answer,
                evaluation=evaluation,
                conversation_context=conversation_context,
            )
            result = self._gemini.generate_json(prompt, FOLLOW_UP_SCHEMA)
            decision = self._normalize(result)
            decision = self._ground(decision, question.get("expects", []))
            logger.info(
                "Follow-up decision for %s/%s: should_follow_up=%s (source=%s)",
                session_id,
                question.get("curriculum_question_id"),
                decision.should_follow_up,
                decision.source,
            )
            return decision
        except Exception as exc:  # noqa: BLE001 - never let Gemini break the interview
            logger.warning(
                "Gemini follow-up decision unavailable for %s; using deterministic "
                "fallback (%s)",
                session_id,
                type(exc).__name__,
            )
            return fallback

    # --- Normalization / grounding --------------------------------------------

    @staticmethod
    def _normalize(result: dict) -> FollowUpDecision:
        """Convert the raw Gemini payload into a decision, rejecting bad shapes."""
        should = bool(result.get("should_follow_up"))
        reason = str(result.get("reason") or "").strip()
        question = str(result.get("question") or "").strip()
        target = str(result.get("target_concept") or "").strip()
        if should:
            if not question:
                raise ValidationError("Follow-up response is missing a question.")
            if not target:
                raise ValidationError("Follow-up response is missing a target concept.")
            return FollowUpDecision(
                should_follow_up=True,
                reason=reason,
                question=question,
                target_concept=target,
                source=AI_SOURCE,
            )
        return FollowUpDecision(
            should_follow_up=False,
            reason=reason,
            question="",
            target_concept=None,
            source=AI_SOURCE,
        )

    @staticmethod
    def _ground(decision: FollowUpDecision, expects: list[str]) -> FollowUpDecision:
        """Force ``target_concept`` to be one of the question's expected concepts.

        Rejects (and thus triggers the fallback) any decision that targets a
        concept the curriculum never supplied, so Gemini can never invent facts.
        """
        if not decision.should_follow_up:
            return decision
        expected = match_expected_concept(decision.target_concept or "", expects or [])
        if expected is None:
            raise ValidationError(
                "Follow-up targets a concept unknown to the curriculum: "
                f"'{decision.target_concept}'"
            )
        return FollowUpDecision(
            should_follow_up=decision.should_follow_up,
            reason=decision.reason,
            question=decision.question,
            target_concept=expected,
            source=decision.source,
        )

    # --- Deterministic fallback ------------------------------------------------

    @staticmethod
    def _deterministic_fallback(question: dict, evaluation: dict) -> FollowUpDecision:
        """Mirror the classic heuristic: probe a gap only when coverage is weak.

        A follow-up fires only when the answer addresses fewer than half of the
        expected concepts (strictly more missing than covered), so a candidate
        who covered most of a question is not nagged about the rest. The probe
        is worded supportively and names a concrete curriculum concept.
        """
        if not question.get("follow_up_allowed", False):
            return FollowUpDecision(
                should_follow_up=False,
                reason="Deterministic fallback: follow-up not allowed for this question.",
                question="",
                target_concept=None,
                source=DETERMINISTIC_SOURCE,
            )
        missing = [concept for concept in evaluation.get("missing", []) if concept]
        covered = [concept for concept in evaluation.get("covered", []) if concept]
        if not missing:
            return FollowUpDecision(
                should_follow_up=False,
                reason="Deterministic fallback: every expected concept was addressed.",
                question="",
                target_concept=None,
                source=DETERMINISTIC_SOURCE,
            )
        if len(covered) >= len(missing):
            return FollowUpDecision(
                should_follow_up=False,
                reason=(
                    "Deterministic fallback: answer covered at least half of the "
                    "expected concepts, so no follow-up is needed."
                ),
                question="",
                target_concept=None,
                source=DETERMINISTIC_SOURCE,
            )
        concept = missing[0]
        return FollowUpDecision(
            should_follow_up=True,
            reason="Deterministic fallback: most expected concepts not addressed.",
            question=(
                f"Let's go a level deeper. Can you tell me more about "
                f"'{concept}' and how it connects to your answer?"
            ),
            target_concept=concept,
            source=DETERMINISTIC_SOURCE,
        )
