"""Tests for the multi-AI answer verification ensemble.

Covers the enabled gating, majority-consensus aggregation (correct vs.
incorrect verdicts, average scoring), per-model failure isolation (a bad or
failing verifier never breaks the panel), score clamping/rounding, and the
grounding of the verification prompt.
"""

from __future__ import annotations

from unittest import mock

from app.services.gemini_service import GeminiService
from app.services.prompt_builder import PromptBuilder, VERIFICATION_SCHEMA
from app.services.verification_service import (
    VERDICT_CORRECT,
    VERDICT_INCORRECT,
    VERDICT_UNVERIFIED,
    AIVerifierEnsemble,
)
from app.utils.config import Settings
from app.utils.errors import LLMError


def _mock_gemini(*results) -> mock.MagicMock:
    gemini = mock.MagicMock()
    gemini.enabled = True
    if results:
        gemini.generate_json.side_effect = list(results)
    return gemini


def _ensemble(gemini, models=("ai-a", "ai-b", "ai-c")) -> AIVerifierEnsemble:
    return AIVerifierEnsemble(
        gemini_service=gemini,
        prompt_builder=PromptBuilder(),
        models=list(models),
    )


def _payload(is_correct: bool, score: float, reasoning: str = "r", feedback: str = "f") -> dict:
    return {
        "is_correct": is_correct,
        "score": score,
        "reasoning": reasoning,
        "feedback": feedback,
    }


def _verify(ensemble, answer: str = "A tuple is immutable, a list is mutable."):
    return ensemble.verify(
        session_id="s1",
        question={
            "curriculum_question_id": "py-q1",
            "text": "Explain the difference between a list and a tuple.",
            "expects": ["immutable", "mutable"],
        },
        answer=answer,
        deterministic={"covered": ["immutable", "mutable"], "missing": []},
    )


class TestEnabledGate:
    def test_disabled_when_gemini_disabled(self) -> None:
        gemini = _mock_gemini()
        gemini.enabled = False
        ensemble = _ensemble(gemini)
        assert ensemble.enabled is False
        assert _verify(ensemble) is None
        gemini.generate_json.assert_not_called()

    def test_disabled_without_models(self) -> None:
        gemini = _mock_gemini()
        ensemble = AIVerifierEnsemble(
            gemini_service=gemini,
            prompt_builder=PromptBuilder(),
            models=[],
        )
        assert ensemble.enabled is False
        assert _verify(ensemble) is None

    def test_empty_answer_never_queries(self) -> None:
        gemini = _mock_gemini()
        ensemble = _ensemble(gemini)
        assert _verify(ensemble, answer="   ") is None
        gemini.generate_json.assert_not_called()


class TestConsensus:
    def test_majority_correct_uses_agreeing_average(self) -> None:
        gemini = _mock_gemini(
            _payload(True, 9.0),
            _payload(True, 8.0),
            _payload(False, 2.0),
        )
        verification = _verify(_ensemble(gemini))
        assert verification is not None
        assert verification.verdict == VERDICT_CORRECT
        assert verification.agreed == 2
        assert verification.total == 3
        assert verification.score == 8.5
        assert "2 of 3" in verification.reasoning
        assert verification.feedback

    def test_majority_incorrect_uses_rejecting_average(self) -> None:
        gemini = _mock_gemini(
            _payload(True, 8.0),
            _payload(False, 3.0),
            _payload(False, 2.0),
        )
        verification = _verify(_ensemble(gemini))
        assert verification is not None
        assert verification.verdict == VERDICT_INCORRECT
        assert verification.agreed == 1
        assert verification.score == 2.5

    def test_unanimous_correct(self) -> None:
        gemini = _mock_gemini(_payload(True, 9.0), _payload(True, 8.0), _payload(True, 7.0))
        verification = _verify(_ensemble(gemini))
        assert verification is not None
        assert verification.verdict == VERDICT_CORRECT
        assert verification.agreed == 3
        assert verification.score == 8.0

    def test_strict_threshold_requires_unanimity(self) -> None:
        gemini = _mock_gemini(
            _payload(True, 9.0),
            _payload(True, 8.0),
            _payload(False, 2.0),
        )
        ensemble = AIVerifierEnsemble(
            gemini_service=gemini,
            prompt_builder=PromptBuilder(),
            models=["ai-a", "ai-b", "ai-c"],
            agreement_threshold=1.0,
        )
        verification = _verify(ensemble)
        assert verification is not None
        assert verification.verdict == VERDICT_INCORRECT
        assert verification.score == 2.0

    def test_scores_are_clamped_and_rounded(self) -> None:
        gemini = _mock_gemini(
            _payload(True, 99.0),
            _payload(True, -5.0),
            _payload(True, 7.123),
        )
        verification = _verify(_ensemble(gemini))
        assert verification is not None
        assert verification.verdict == VERDICT_CORRECT
        assert verification.score == round((10.0 + 0.0 + 7.12) / 3, 2)


class TestFailureIsolation:
    def test_failing_verifier_is_skipped(self) -> None:
        gemini = _mock_gemini(
            _payload(True, 9.0),
            LLMError("boom"),
            _payload(True, 7.0),
        )
        verification = _verify(_ensemble(gemini))
        assert verification is not None
        assert verification.verdict == VERDICT_CORRECT
        assert verification.total == 2
        assert verification.score == 8.0

    def test_malformed_payload_skips_that_verifier(self) -> None:
        gemini = _mock_gemini(
            _payload(True, 9.0),
            {"score": 7.0, "reasoning": "missing verdict"},
            _payload(True, 8.0),
        )
        verification = _verify(_ensemble(gemini))
        assert verification is not None
        assert verification.total == 2
        assert verification.score == 8.5

    def test_all_verifiers_failing_returns_none(self) -> None:
        gemini = _mock_gemini(LLMError("a"), LLMError("b"), LLMError("c"))
        assert _verify(_ensemble(gemini)) is None


class TestPrompt:
    def test_prompt_uses_verification_schema_and_one_call_per_model(self) -> None:
        gemini = _mock_gemini(_payload(True, 9.0), _payload(True, 8.0), _payload(True, 7.0))
        _verify(_ensemble(gemini, models=("v1", "v2", "v3")))
        assert gemini.generate_json.call_count == 3
        for call in gemini.generate_json.call_args_list:
            args, kwargs = call
            assert args[1] == VERIFICATION_SCHEMA
            assert kwargs["model"] in {"v1", "v2", "v3"}

    def test_prompt_is_grounded_with_question(self) -> None:
        gemini = _mock_gemini(_payload(True, 9.0), _payload(True, 8.0), _payload(True, 7.0))
        _verify(_ensemble(gemini, models=("v1",)))
        prompt = gemini.generate_json.call_args.args[0]
        assert "Explain the difference between a list and a tuple." in prompt
        assert "immutable" in prompt
