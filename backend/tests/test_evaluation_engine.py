"""Focused tests for the hardened deterministic EvaluationEngine.

Covers the structured :class:`AnswerEvaluation` contract, the deterministic
``coverage x length`` scoring strategy (empty / short / complete / partial
answers, case handling, duplicate mentions, score bounds, determinism), the
grounding guarantee (only curriculum ``expects`` concepts are ever reported),
and persistence through the existing ScoreRepository.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from app.database.connection import Database
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.models.common import utc_now
from app.services.evaluation_engine import (
    MIN_ANSWER_TOKENS,
    AnswerEvaluation,
    COMPLETENESS_COMPLETE,
    COMPLETENESS_EMPTY,
    COMPLETENESS_PARTIAL,
    COMPLETENESS_UNSATISFACTORY,
    EvaluationEngine,
)
from app.services.gemini_service import GeminiService
from app.services.prompt_builder import EVALUATION_SCHEMA, PromptBuilder
from app.utils.config import Settings

EXPECTS = ["immutable", "mutable"]


def _build_engine(tmp_path: Path, session_id: str = "s1") -> EvaluationEngine:
    """A wired engine backed by a temp SQLite database.

    A session row is created up front because ``scores.session_id`` references
    ``sessions(id)``.
    """
    db = Database(tmp_path / "evaluation.db")
    db.initialize()
    SessionRepository(db).create(
        session_id=session_id,
        candidate_id="candidate-001",
        curriculum_id="curriculum-001",
        now=utc_now(),
    )
    return EvaluationEngine(
        gemini_service=GeminiService(settings=Settings(gemini_enabled=False)),
        score_repository=ScoreRepository(db),
        message_repository=MessageRepository(db),
    )


def _score_penalty(factor: float) -> float:
    """Expected score for full coverage under ``factor``-token length."""
    return round(10.0 * factor / MIN_ANSWER_TOKENS, 2)


# --- Empty / very short answers ----------------------------------------------


class TestEmptyAndShortAnswers:
    def test_empty_answer(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail("s1", "t1", "q1", "", expects=EXPECTS)
        assert ev.score == 0.0
        assert ev.matched_concepts == []
        assert ev.missing_concepts == EXPECTS
        assert ev.coverage == 0.0
        assert ev.completeness == COMPLETENESS_EMPTY
        assert ev.feedback

    def test_blank_whitespace_answer(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail("s1", "t1", "q1", "   \n\t ", expects=EXPECTS)
        assert ev.score == 0.0
        assert ev.completeness == COMPLETENESS_EMPTY

    def test_single_word_answer_is_penalized(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail("s1", "t1", "q1", "immutable", expects=EXPECTS)
        assert ev.matched_concepts == ["immutable"]
        assert ev.coverage == 0.5
        assert ev.completeness == COMPLETENESS_PARTIAL
        assert 0.0 < ev.score < 10.0
        assert ev.score == round(10.0 * 0.5 / MIN_ANSWER_TOKENS, 2)

    def test_label_listing_does_not_earn_full_marks(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail("s1", "t1", "q1", "immutable mutable", expects=EXPECTS)
        assert ev.coverage == 1.0
        assert ev.completeness == COMPLETENESS_PARTIAL
        assert ev.score == _score_penalty(2.0)
        assert ev.score < 10.0


# --- Complete / partial answers ----------------------------------------------


class TestCompleteAndPartial:
    def test_complete_expected_concept_answer(self, tmp_path: Path) -> None:
        answer = "A list is mutable while a tuple is immutable; mutability is the key difference."
        ev = _build_engine(tmp_path).evaluate_answer_detail("s1", "t1", "q1", answer, expects=EXPECTS)
        assert ev.score == 10.0
        assert ev.coverage == 1.0
        assert ev.completeness == COMPLETENESS_COMPLETE
        assert ev.matched_concepts == ["immutable", "mutable"]
        assert ev.missing_concepts == []

    def test_partial_answer(self, tmp_path: Path) -> None:
        answer = "A tuple cannot be changed after creation, so it is immutable."
        ev = _build_engine(tmp_path).evaluate_answer_detail("s1", "t1", "q1", answer, expects=EXPECTS)
        assert ev.matched_concepts == ["immutable"]
        assert ev.missing_concepts == ["mutable"]
        assert ev.coverage == 0.5
        assert ev.completeness == COMPLETENESS_PARTIAL
        assert ev.score == 5.0

    def test_nothing_addressed_is_unsatisfactory(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "I am not sure about this one.", expects=EXPECTS
        )
        assert ev.score == 0.0
        assert ev.matched_concepts == []
        assert ev.missing_concepts == EXPECTS
        assert ev.completeness == COMPLETENESS_UNSATISFACTORY


# --- Curriculum grounding ----------------------------------------------------


class TestConceptGrounding:
    def test_missing_concepts_are_only_from_curriculum(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "hashmap caching sharding", expects=["immutable", "mutable"]
        )
        assert ev.matched_concepts == []
        assert ev.missing_concepts == EXPECTS

    def test_no_concepts_outside_expects_are_invented(self, tmp_path: Path) -> None:
        engine = _build_engine(tmp_path)
        for answer in ["immutable", "mutable", "immutable and mutable are both covered here", "irrelevant"]:
            ev = engine.evaluate_answer_detail("s1", "t1", "q1", answer, expects=EXPECTS)
            combined = ev.matched_concepts + ev.missing_concepts
            assert set(combined) == set(EXPECTS)
            assert set(combined) <= set(EXPECTS)

    def test_no_expected_concepts_gets_full_credit(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail("s1", "t1", "q1", "whatever", expects=[])
        assert ev.score == 10.0
        assert ev.completeness == COMPLETENESS_COMPLETE
        assert ev.matched_concepts == []
        assert ev.missing_concepts == []


# --- Lexical robustness ------------------------------------------------------


class TestLexicalRobustness:
    def test_case_differences(self, tmp_path: Path) -> None:
        engine = _build_engine(tmp_path)
        lower = engine.evaluate_answer_detail("s1", "t1", "q1", "a list is mutable and a tuple is immutable", expects=EXPECTS)
        upper = engine.evaluate_answer_detail("s1", "t1", "q1", "A LIST IS MUTABLE AND A TUPLE IS IMMUTABLE", expects=EXPECTS)
        assert lower.score == upper.score
        assert lower.matched_concepts == upper.matched_concepts == ["immutable", "mutable"]
        assert lower.completeness == upper.completeness == COMPLETENESS_COMPLETE

    def test_duplicate_concept_mentions_do_not_inflate_score(self, tmp_path: Path) -> None:
        repeated = "immutable " * 50
        ev = _build_engine(tmp_path).evaluate_answer_detail("s1", "t1", "q1", repeated, expects=["immutable"])
        assert ev.matched_concepts == ["immutable"]
        assert ev.coverage == 1.0
        assert ev.score < 10.0
        assert ev.score == round(10.0 * 1.0 / MIN_ANSWER_TOKENS, 2)

    def test_multi_word_concept_matches_derived_word_forms(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "We used load balancing across replicas.", expects=["load balancer"]
        )
        assert ev.matched_concepts == ["load balancer"]
        assert ev.missing_concepts == []

    def test_multi_word_concept_requires_all_tokens(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "We spread requests evenly across several replicas.", expects=["load balancer"]
        )
        assert ev.matched_concepts == []
        assert ev.missing_concepts == ["load balancer"]

    def test_multi_word_concept_matches_when_all_tokens_present(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "The load balancer distributes traffic evenly.", expects=["load balancer"]
        )
        assert ev.matched_concepts == ["load balancer"]
        assert ev.coverage == 1.0
        assert ev.completeness == COMPLETENESS_COMPLETE
        assert ev.score == 10.0


# --- Stem-aware matching & concept aliases ------------------------------------


class TestStemmingAndAliases:
    def test_performs_matches_performance(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1",
            "A tuple performs well because it is smaller in memory.",
            expects=["performance"],
        )
        assert ev.matched_concepts == ["performance"]
        assert ev.missing_concepts == []

    def test_caching_matches_cache(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1",
            "The system caches responses to speed up lookups.",
            expects=["caching"],
        )
        assert ev.matched_concepts == ["caching"]

    def test_balancing_matches_load_balancer(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1",
            "We added a load balancing layer in front of the servers.",
            expects=["load balancer"],
        )
        assert ev.matched_concepts == ["load balancer"]
        assert ev.missing_concepts == []

    def test_mutable_paraphrase(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "Lists can change after creation.", expects=["mutable"]
        )
        assert ev.matched_concepts == ["mutable"]

    def test_immutable_paraphrase(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "Tuples cannot be modified.", expects=["immutable"]
        )
        assert ev.matched_concepts == ["immutable"]

    def test_abbreviation_gil(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1",
            "The GIL prevents true parallelism in threads.",
            expects=["global interpreter lock"],
        )
        assert ev.matched_concepts == ["global interpreter lock"]

    def test_correct_paraphrase_no_longer_scores_zero(self, tmp_path: Path) -> None:
        paraphrased = "Lists can change after creation but tuples cannot be modified."
        engine = _build_engine(tmp_path)
        expects = ["immutable", "mutable", "performance", "hashable"]
        ev = engine.evaluate_answer_detail("s1", "t1", "q1", paraphrased, expects=expects)
        assert ev.matched_concepts == ["immutable", "mutable"]
        assert ev.score == 5.0


class TestNaturalLanguageMatching:
    """Correct, ordinary-language answers should earn fair credit, and never
    be punished for avoiding the exact curriculum vocabulary."""

    def test_performance_matches_less_memory(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1",
            "A tuple uses less memory than a list and can be a dictionary key.",
            expects=["performance", "hashable"],
        )
        assert ev.matched_concepts == ["performance", "hashable"]
        assert ev.missing_concepts == []
        assert ev.score == 10.0

    def test_hashable_matches_used_as_keys(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1",
            "Tuples can be used as keys in dictionaries because they never change.",
            expects=["immutable", "hashable"],
        )
        assert ev.matched_concepts == ["immutable", "hashable"]
        assert ev.score == 10.0

    def test_memory_address_matches_in_memory(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1",
            "The is operator checks whether two variables point at the same object in memory.",
            expects=["identity", "memory address"],
        )
        assert ev.matched_concepts == ["identity", "memory address"]
        assert ev.missing_concepts == []
        assert ev.score == 10.0

    def test_full_ai_quality_answer_scores_full_marks(self, tmp_path: Path) -> None:
        answer = (
            "A list is a mutable sequence that you can change after you create it, "
            "while a tuple is fixed-size and unchangeable once created. Tuples take "
            "less memory and can be used as keys in dictionaries, while lists cannot "
            "because they can change."
        )
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", answer,
            expects=["immutable", "mutable", "performance", "hashable"],
        )
        assert ev.score == 10.0
        assert ev.missing_concepts == []

    def test_partial_credit_for_partially_matched_concept(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1",
            "each node stores a value and has two children",
            expects=["node ordering"],
        )
        assert ev.matched_concepts == []
        assert ev.missing_concepts == ["node ordering"]
        assert ev.score == 5.0
        assert ev.coverage == 0.5

    def test_stray_word_does_not_partially_credit(self, tmp_path: Path) -> None:
        """A lone stopword inside a multi-word alias must not grant credit."""
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "I am not sure about this one.",
            expects=["immutable", "mutable"],
        )
        assert ev.matched_concepts == []
        assert ev.score == 0.0


# --- Score bounds / determinism ----------------------------------------------


class TestScoreBoundsAndDeterminism:
    def test_score_always_between_zero_and_ten(self, tmp_path: Path) -> None:
        engine = _build_engine(tmp_path)
        answers = [
            "",
            "immutable",
            "mutable",
            "immutable mutable",
            "a full and complete answer mentioning immutable and mutable",
            "nothing relevant",
            "x" * 500,
        ]
        for answer in answers:
            ev = engine.evaluate_answer_detail("s1", "t1", "q1", answer, expects=EXPECTS)
            assert 0.0 <= ev.score <= 10.0

    def test_deterministic_repeated_evaluation(self, tmp_path: Path) -> None:
        engine = _build_engine(tmp_path)
        answer = "A list is mutable while a tuple is immutable."
        first = engine.evaluate_answer_detail("s1", "t1", "q1", answer, expects=EXPECTS)
        second = engine.evaluate_answer_detail("s1", "t1", "q1", answer, expects=EXPECTS)
        assert first == second
        assert first.score == second.score
        assert first.feedback == second.feedback
        assert first.completeness == second.completeness

    def test_structured_evaluation_carries_all_signals(self, tmp_path: Path) -> None:
        ev = _build_engine(tmp_path).evaluate_answer_detail(
            "s1", "t1", "q1", "A tuple is immutable while a list is mutable.", expects=EXPECTS
        )
        assert isinstance(ev, AnswerEvaluation)
        assert ev.score == 10.0
        assert ev.coverage == 1.0
        assert ev.expected_concepts == 2
        assert ev.reasoning is None


# --- Persistence -------------------------------------------------------------


class TestPersistence:
    def test_score_persisted_via_score_repository(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "evaluation.db")
        db.initialize()
        SessionRepository(db).create(
            session_id="sess-1",
            candidate_id="candidate-001",
            curriculum_id="curriculum-001",
            now=utc_now(),
        )
        score_repo = ScoreRepository(db)
        engine = EvaluationEngine(
            gemini_service=GeminiService(settings=Settings(gemini_enabled=False)),
            score_repository=score_repo,
            message_repository=MessageRepository(db),
        )
        engine.evaluate_answer("sess-1", "topic-1", "q-1", "A tuple is immutable and a list is mutable.", expects=EXPECTS)

        rows = score_repo.list_by_session("sess-1")
        assert len(rows) == 1
        row = rows[0]
        assert row["session_id"] == "sess-1"
        assert row["topic_id"] == "topic-1"
        assert row["question_id"] == "q-1"
        assert row["score"] == 10.0
        assert 0.0 <= row["score"] <= 10.0
        assert row["rationale"]

    def test_evaluate_answer_returns_float_and_persists(self, tmp_path: Path) -> None:
        engine = _build_engine(tmp_path)
        result = engine.evaluate_answer("s1", "t1", "q1", "A tuple is immutable while a list is mutable.", expects=EXPECTS)
        assert isinstance(result, float)
        assert result == 10.0

    @pytest.mark.parametrize(
        "answer, expected_score",
        [
            ("", 0.0),
            ("immutable", round(10.0 * 0.5 / MIN_ANSWER_TOKENS, 2)),
            ("A tuple is immutable and a list is mutable.", 10.0),
        ],
    )
    def test_persisted_score_matches_evaluation(
        self, tmp_path: Path, answer: str, expected_score: float
    ) -> None:
        engine = _build_engine(tmp_path, "sess-p")
        ev = engine.evaluate_answer_detail("sess-p", "topic-p", "q-p", answer, expects=EXPECTS)
        row = engine._scores.list_by_session("sess-p")[0]
        assert ev.score == expected_score
        assert row["score"] == expected_score


# --- AI semantic evaluation ---------------------------------------------------


def _build_ai_engine(tmp_path: Path, gemini, session_id: str = "s1", db_name: str = "ai_evaluation.db") -> EvaluationEngine:
    """A wired engine (with PromptBuilder) whose Gemini is ``gemini``."""
    db = Database(tmp_path / db_name)
    db.initialize()
    SessionRepository(db).create(
        session_id=session_id,
        candidate_id="candidate-001",
        curriculum_id="curriculum-001",
        now=utc_now(),
    )
    return EvaluationEngine(
        gemini_service=gemini,
        score_repository=ScoreRepository(db),
        message_repository=MessageRepository(db),
        prompt_builder=PromptBuilder(),
    )


def _mock_gemini(result: dict | None = None, error: Exception | None = None) -> mock.MagicMock:
    gemini = mock.MagicMock()
    gemini.enabled = True
    if error is not None:
        gemini.generate_json.side_effect = error
    else:
        gemini.generate_json.return_value = result
    return gemini


QUESTION = {
    "curriculum_question_id": "py-q1",
    "text": "Explain the difference between a list and a tuple.",
    "difficulty": "easy",
    "expects": ["immutable", "mutable", "performance", "hashable"],
}


class TestAiEvaluation:
    def test_ai_score_reasoning_and_feedback_are_adopted(self, tmp_path: Path) -> None:
        payload = {
            "score": 8.5,
            "covered": ["immutable", "mutable"],
            "missing": ["performance"],
            "reasoning": "Correct distinction; depth is good.",
            "feedback": "You clearly explained the core difference.",
        }
        engine = _build_ai_engine(tmp_path, _mock_gemini(payload))
        ev = engine.evaluate_answer_detail(
            "s1", "topic-python", "py-q1",
            "A list can be changed while a tuple cannot.",
            expects=QUESTION["expects"],
            question=QUESTION,
        )
        assert ev.score == 8.5
        assert ev.reasoning == "Correct distinction; depth is good."
        assert ev.feedback == "You clearly explained the core difference."
        assert ev.matched_concepts == ["immutable", "mutable"]
        assert ev.missing_concepts == ["performance"]
        assert ev.completeness == COMPLETENESS_COMPLETE

    def test_ai_concepts_are_grounded_to_expects(self, tmp_path: Path) -> None:
        payload = {
            "score": 6.0,
            "covered": ["immutable", "invented concept"],
            "missing": ["mutable", "made-up thing"],
            "reasoning": "r",
            "feedback": "f",
        }
        engine = _build_ai_engine(tmp_path, _mock_gemini(payload))
        ev = engine.evaluate_answer_detail(
            "s1", "topic-python", "py-q1", "answer", expects=QUESTION["expects"], question=QUESTION
        )
        assert ev.matched_concepts == ["immutable"]
        assert ev.missing_concepts == ["mutable"]

    def test_ai_score_is_clamped_to_zero_ten(self, tmp_path: Path) -> None:
        for index, (raw, expected) in enumerate([(99.0, 10.0), (-5.0, 0.0), (7.123, 7.12)]):
            gemini = _mock_gemini(
                {"score": raw, "covered": [], "missing": [], "reasoning": "", "feedback": ""}
            )
            ev = _build_ai_engine(tmp_path, gemini, db_name=f"ai_evaluation_{index}.db").evaluate_answer_detail(
                "s1", "topic-python", f"py-q{index}", "answer", expects=QUESTION["expects"], question=QUESTION
            )
            assert ev.score == expected

    def test_prompt_is_grounded_with_schema_and_question(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(
            {"score": 9.0, "covered": ["immutable"], "missing": [], "reasoning": "", "feedback": ""}
        )
        _build_ai_engine(tmp_path, gemini).evaluate_answer_detail(
            "s1", "topic-python", "py-q1",
            "A tuple is immutable, a list is mutable.",
            expects=QUESTION["expects"],
            question=QUESTION,
        )
        prompt, schema = gemini.generate_json.call_args.args
        assert schema == EVALUATION_SCHEMA
        assert QUESTION["text"] in prompt
        assert "immutable" in prompt

    def test_disabled_gemini_uses_deterministic(self, tmp_path: Path) -> None:
        gemini = _mock_gemini({"score": 9.0, "covered": [], "missing": [], "reasoning": "", "feedback": ""})
        gemini.enabled = False
        ev = _build_ai_engine(tmp_path, gemini).evaluate_answer_detail(
            "s1", "topic-python", "py-q1", "answer", expects=EXPECTS, question=QUESTION
        )
        gemini.generate_json.assert_not_called()
        assert ev.score == 0.0
        assert ev.reasoning is None

    def test_gemini_failure_falls_back_to_deterministic(self, tmp_path: Path) -> None:
        from app.utils.errors import LLMError

        gemini = _mock_gemini(error=LLMError("boom"))
        ev = _build_ai_engine(tmp_path, gemini).evaluate_answer_detail(
            "s1", "topic-python", "py-q1",
            "A tuple is immutable while a list is mutable.",
            expects=EXPECTS,
            question=QUESTION,
        )
        assert ev.score == 10.0
        assert ev.matched_concepts == ["immutable", "mutable"]

    def test_empty_answer_never_calls_gemini(self, tmp_path: Path) -> None:
        gemini = _mock_gemini({"score": 9.0, "covered": [], "missing": [], "reasoning": "", "feedback": ""})
        ev = _build_ai_engine(tmp_path, gemini).evaluate_answer_detail(
            "s1", "topic-python", "py-q1", "   ", expects=EXPECTS, question=QUESTION
        )
        gemini.generate_json.assert_not_called()
        assert ev.score == 0.0
        assert ev.completeness == COMPLETENESS_EMPTY
