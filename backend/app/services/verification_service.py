"""Multi-AI answer verification.

Cross-checks a candidate's answer with a panel of independent AI models before
it is graded. Each model independently judges whether the answer is correct and
awards its own 0-10 mark; the ensemble then combines the votes into a consensus
verdict and a single score:

* at least ``agreement_threshold`` (default majority) of the AIs confirm the
  answer -> verdict ``correct`` and the mark is the average of the confirming
  AIs' scores;
* otherwise -> verdict ``incorrect`` and the mark is the average of the
  rejecting AIs' scores (which are low by construction), so an answer that
  fails verification can never earn a passing grade from a single lenient model.

Every AI runs independently and concurrently. Any individual model that errors,
times out, or returns a malformed payload is skipped; the verdict is built from
the surviving votes. If no vote survives, or the panel is disabled, the caller
falls back to the deterministic scorer — an AI can never break scoring.

Collaborators: GeminiService (per-model calls), PromptBuilder.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.services.gemini_service import GeminiService
from app.services.prompt_builder import VERIFICATION_SCHEMA, PromptBuilder
from app.utils.errors import ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

VERDICT_CORRECT = "correct"
VERDICT_INCORRECT = "incorrect"
VERDICT_UNVERIFIED = "unverified"

#: Cap on how many models are queried at once (each call is independent).
DEFAULT_MAX_CONCURRENT = 4


@dataclass(frozen=True)
class VerifierVote:
    """A single AI model's independent verdict and mark."""

    model: str
    is_correct: bool
    score: float
    reasoning: str = ""
    feedback: str = ""


@dataclass(frozen=True)
class Verification:
    """The consensus result of the AI verification panel."""

    verdict: str
    score: float
    agreed: int
    total: int
    votes: tuple[VerifierVote, ...] = ()
    reasoning: str = ""
    feedback: str = ""


class AIVerifierEnsemble:
    """Queries a panel of AI models and aggregates their verdicts."""

    def __init__(
        self,
        gemini_service: GeminiService,
        prompt_builder: PromptBuilder,
        models: list[str],
        *,
        agreement_threshold: float = 0.5,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> None:
        self._gemini = gemini_service
        self._builder = prompt_builder
        self._models = [model for model in (models or []) if model and model.strip()]
        self._threshold = agreement_threshold
        self._max_concurrent = max(1, max_concurrent)

    @property
    def enabled(self) -> bool:
        """Return True only when the underlying AI is on AND models are set."""
        return self._gemini.enabled and bool(self._models)

    def verify(
        self,
        session_id: str,
        question: dict,
        answer: str,
        deterministic: dict,
    ) -> Verification | None:
        """Return the consensus verification, or ``None`` when none could be produced.

        ``question`` is the plan question (``text``/``expects``) grounding the
        prompt; ``deterministic`` carries the grounded coverage signal
        (``covered``/``missing`` lists). ``None`` signals the caller to fall
        back to the deterministic scorer.
        """
        if not self.enabled:
            return None
        if not answer.strip():
            return None
        votes = self._collect_votes(session_id, question, answer, deterministic)
        if not votes:
            logger.warning(
                "AI verification unavailable for %s: every verifier failed.",
                session_id,
            )
            return None
        return self._aggregate(votes)

    def _collect_votes(
        self,
        session_id: str,
        question: dict,
        answer: str,
        deterministic: dict,
    ) -> list[VerifierVote]:
        """Query every verifier model concurrently and return the valid votes."""
        prompt = self._builder.build_verification_prompt(
            session_id=session_id,
            question=question,
            answer=answer,
            deterministic=deterministic,
        )

        def run(model: str) -> VerifierVote | None:
            try:
                result = self._gemini.generate_json(prompt, VERIFICATION_SCHEMA, model=model)
                return self._normalize_vote(model, result)
            except Exception as exc:  # noqa: BLE001 - skip one bad verifier
                logger.warning(
                    "Verifier %s skipped for %s (%s).",
                    model,
                    session_id,
                    type(exc).__name__,
                )
                return None

        with ThreadPoolExecutor(
            max_workers=min(self._max_concurrent, len(self._models))
        ) as pool:
            results = list(pool.map(run, self._models))
        return [vote for vote in results if vote is not None]

    @staticmethod
    def _normalize_vote(model: str, result: dict) -> VerifierVote:
        """Convert one raw Gemini payload into a validated :class:`VerifierVote`.

        Raises ``ValidationError`` for malformed payloads so the ensemble can
        skip this verifier without affecting the others.
        """
        is_correct = result.get("is_correct")
        if not isinstance(is_correct, bool):
            raise ValidationError("Verification must include a boolean 'is_correct' verdict.")
        raw_score = result.get("score")
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            raise ValidationError("Verification score must be a number.")
        return VerifierVote(
            model=model,
            is_correct=is_correct,
            score=round(max(0.0, min(10.0, float(raw_score))), 2),
            reasoning=str(result.get("reasoning") or "").strip(),
            feedback=str(result.get("feedback") or "").strip(),
        )

    def _aggregate(self, votes: list[VerifierVote]) -> Verification:
        """Combine the panel's votes into a consensus verdict and score."""
        total = len(votes)
        agreeing = [vote for vote in votes if vote.is_correct]
        rejecting = [vote for vote in votes if not vote.is_correct]
        agreement = len(agreeing) / total

        if agreement >= self._threshold:
            verdict = VERDICT_CORRECT
            consensus = agreeing
            reasoning = (
                f"{len(agreeing)} of {total} AI models verified this answer as correct."
            )
        else:
            verdict = VERDICT_INCORRECT
            consensus = rejecting or agreeing
            reasoning = (
                f"Only {len(agreeing)} of {total} AI models verified this answer as correct."
            )

        score = sum(vote.score for vote in consensus) / len(consensus)
        lead = max(consensus, key=lambda vote: vote.score)
        if lead.feedback:
            feedback = lead.feedback
        else:
            feedback = reasoning
        if lead.reasoning:
            reasoning = f"{reasoning} {lead.reasoning}".strip()

        return Verification(
            verdict=verdict,
            score=round(score, 2),
            agreed=len(agreeing),
            total=total,
            votes=tuple(votes),
            reasoning=reasoning,
            feedback=feedback,
        )
