"""Adaptive per-turn interview decisions.

The ``AdaptiveDecider`` owns the "what happens next" decision after every
primary answer: ask exactly one follow-up, advance to the next primary, or end
the interview. Unlike the classic concept-coverage heuristic, the decider
considers the full picture — the candidate's actual answer, the deterministic
evaluation, the recent conversation, how many primary questions remain, and the
plan's difficulty bias — and can therefore decline follow-ups it deems
unnecessary or request completion only when the plan is exhausted.

Follow-up questions are grounded the same way as the adaptive follow-up layer:
the AI may produce at most one follow-up whose target concept must be one of the
question's expected concepts (reusing ``FollowUpAdvisor`` helpers), and every
Gemini failure (disabled, unavailable, LLM error, malformed JSON, unknown target
concept, unexpected exception) degrades gracefully to the deterministic decision
so the LLM can never terminate or derail an interview.

Collaborators: PromptBuilder, GeminiService, FollowUpAdvisor.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.services.follow_up_advisor import (
    AI_SOURCE,
    DETERMINISTIC_SOURCE,
    FollowUpAdvisor,
    match_expected_concept,
)
from app.services.gemini_service import GeminiService
from app.services.prompt_builder import DECISION_SCHEMA, PromptBuilder
from app.utils.errors import ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

ACTION_FOLLOW_UP = "follow_up"
ACTION_NEXT = "next_question"
ACTION_COMPLETE = "complete"
VALID_ACTIONS = {ACTION_FOLLOW_UP, ACTION_NEXT, ACTION_COMPLETE}


@dataclass(frozen=True)
class InterviewDecision:
    """The next interview action after one primary answer."""

    action: str  # one of ACTION_*: follow_up | next_question | complete
    reason: str
    question: str  # the single follow-up text when action == "follow_up"
    target_concept: str | None
    source: str  # "ai" | "deterministic"


class AdaptiveDecider:
    """Produces one grounded decision per primary answer."""

    def __init__(
        self,
        prompt_builder: PromptBuilder,
        gemini_service: GeminiService,
        follow_up_advisor: FollowUpAdvisor,
    ) -> None:
        self._builder = prompt_builder
        self._gemini = gemini_service
        self._advisor = follow_up_advisor

    def decide(
        self,
        *,
        session_id: str,
        topic: dict,
        question: dict,
        answer: str,
        evaluation: dict,
        conversation_context: list[dict],
        remaining_questions: int,
        difficulty_bias: str | None,
    ) -> InterviewDecision:
        """Return the next-action decision, always safe to consume.

        Uses Gemini when enabled and falls back to the deterministic rules on
        any failure. The engine remains authoritative over the plan length: it
        may coerce a premature ``complete`` or a spurious ``next_question``.
        """
        fallback = self._deterministic(question, evaluation, remaining_questions)
        if not self._gemini.enabled:
            logger.info(
                "Gemini decision disabled; using deterministic decision for %s/%s",
                session_id,
                question.get("curriculum_question_id"),
            )
            return fallback

        try:
            prompt = self._builder.build_decision_prompt(
                session_id=session_id,
                topic=topic,
                question=question,
                answer=answer,
                evaluation=evaluation,
                conversation_context=conversation_context,
                remaining_questions=remaining_questions,
                difficulty_bias=difficulty_bias,
            )
            result = self._gemini.generate_json(prompt, DECISION_SCHEMA)
            decision = self._normalize(result)
            decision = self._ground(decision, question.get("expects", []))
            logger.info(
                "Decision for %s/%s: action=%s (source=%s)",
                session_id,
                question.get("curriculum_question_id"),
                decision.action,
                decision.source,
            )
            return decision
        except Exception as exc:  # noqa: BLE001 - never let Gemini break the interview
            logger.warning(
                "Gemini decision unavailable for %s; using deterministic "
                "fallback (%s)",
                session_id,
                type(exc).__name__,
            )
            return fallback

    # --- Deterministic rules --------------------------------------------------

    @staticmethod
    def _deterministic(
        question: dict,
        evaluation: dict,
        remaining_questions: int,
    ) -> InterviewDecision:
        """Classic rules: exhaust the plan, then probe the first missing concept."""
        if remaining_questions <= 0:
            return InterviewDecision(
                action=ACTION_COMPLETE,
                reason="Deterministic: no primary questions remain.",
                question="",
                target_concept=None,
                source=DETERMINISTIC_SOURCE,
            )

        follow_up = FollowUpAdvisor._deterministic_fallback(question, evaluation)
        if follow_up.should_follow_up:
            return InterviewDecision(
                action=ACTION_FOLLOW_UP,
                reason=follow_up.reason,
                question=follow_up.question,
                target_concept=follow_up.target_concept,
                source=DETERMINISTIC_SOURCE,
            )
        return InterviewDecision(
            action=ACTION_NEXT,
            reason=follow_up.reason,
            question="",
            target_concept=None,
            source=DETERMINISTIC_SOURCE,
        )

    # --- Normalization / grounding --------------------------------------------

    @staticmethod
    def _normalize(result: dict) -> InterviewDecision:
        """Convert the raw Gemini payload into a decision, rejecting bad shapes."""
        action = str(result.get("action") or "").strip().lower()
        reason = str(result.get("reason") or "").strip()
        question = str(result.get("question") or "").strip()
        target = str(result.get("target_concept") or "").strip()
        if action not in VALID_ACTIONS:
            raise ValidationError(f"Decision carries an unknown action: '{action}'")
        if action == ACTION_FOLLOW_UP:
            if not question:
                raise ValidationError("Decision is missing a follow-up question.")
            if not target:
                raise ValidationError("Decision is missing a target concept.")
        return InterviewDecision(
            action=action,
            reason=reason,
            question=question,
            target_concept=target or None,
            source=AI_SOURCE,
        )

    @staticmethod
    def _ground(
        decision: InterviewDecision,
        expects: list[str],
    ) -> InterviewDecision:
        """Force a follow-up target onto the curriculum's expected concepts.

        Any follow-up that names a concept the curriculum never supplied is
        rejected (falling back to the deterministic decision via the caller's
        exception handler), so the LLM can never invent facts.
        """
        if decision.action != ACTION_FOLLOW_UP:
            return decision
        expected = match_expected_concept(decision.target_concept or "", expects or [])
        if expected is None:
            raise ValidationError(
                "Decision targets a concept unknown to the curriculum: "
                f"'{decision.target_concept}'"
            )
        return replace(decision, target_concept=expected)
