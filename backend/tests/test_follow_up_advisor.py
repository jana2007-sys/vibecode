"""Focused tests for AI-generated adaptive follow-up questions.

Covers the PromptBuilder follow-up prompt, the FollowUpAdvisor decision/fallback
logic, and the InterviewEngine integration. Gemini is fully mocked — no real
API calls are made. The deterministic path is exercised by the existing
``test_interview_engine`` suite; these tests add the adaptive layer on top.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from app.database.connection import Database
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.memory.conversation_memory import ConversationMemory
from app.models.candidate import CandidateProfile, SkillLevel
from app.models.session import InterviewState
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator
from app.services.follow_up_advisor import AI_SOURCE, DETERMINISTIC_SOURCE, FollowUpAdvisor
from app.services.gemini_service import GeminiService
from app.services.interview_engine import InterviewEngine
from app.services.memory_engine import MemoryEngine
from app.services.prompt_builder import FOLLOW_UP_SCHEMA, PromptBuilder
from app.services.question_planner import QuestionPlanner
from app.services.session_manager import SessionManager
from app.utils.config import Settings
from app.utils.errors import LLMError, LLMUnavailableError, ValidationError

#: Synthetic 5-topic curriculum with 14 grounded questions (8-primary plans).
SYNTHETIC_CURRICULUM = {
    "id": "curriculum-001",
    "title": "Synthetic Interview Curriculum",
    "description": "Five topics with varied-difficulty questions for follow-up tests.",
    "version": "1.0.0",
    "topics": [
        {
            "id": "topic-python",
            "title": "Python Fundamentals",
            "description": "Data structures, comprehensions, typing, and common idioms.",
            "questions": [
                {"id": "py-e1", "text": "Explain the difference between a list and a tuple.", "difficulty": "easy", "expects": ["immutable", "mutable"]},
                {"id": "py-m1", "text": "What is the difference between a list comprehension and a generator?", "difficulty": "medium", "expects": ["iterator", "lazy"]},
                {"id": "py-h1", "text": "How would you design a memoizing decorator?", "difficulty": "hard", "expects": ["closure", "memoization"]},
            ],
        },
        {
            "id": "topic-databases",
            "title": "Databases & SQL",
            "description": "Relational modeling, indexing, and query performance.",
            "questions": [
                {"id": "db-e1", "text": "Explain the differences between a primary key and a foreign key.", "difficulty": "easy", "expects": ["unique", "relationship"]},
                {"id": "db-m1", "text": "How does a B-tree index speed up query lookups?", "difficulty": "medium", "expects": ["logarithmic", "index"]},
                {"id": "db-h1", "text": "When would you choose a NoSQL store over a relational database?", "difficulty": "hard", "expects": ["consistency", "scaling"]},
            ],
        },
        {
            "id": "topic-systems",
            "title": "System Design",
            "description": "Scalability, APIs, caching, and distributed systems basics.",
            "questions": [
                {"id": "sd-e1", "text": "Explain what an API endpoint is.", "difficulty": "easy", "expects": ["http", "request"]},
                {"id": "sd-m1", "text": "Design a URL shortener. What are the key components?", "difficulty": "medium", "expects": ["caching", "load balancer"]},
                {"id": "sd-h1", "text": "How would you scale a read-heavy web service?", "difficulty": "hard", "expects": ["read replicas", "availability"]},
            ],
        },
        {
            "id": "topic-testing",
            "title": "Software Testing",
            "description": "Testing strategies and techniques.",
            "questions": [
                {"id": "ts-e1", "text": "Explain the difference between unit and integration tests.", "difficulty": "easy", "expects": ["isolation", "scope"]},
                {"id": "ts-m1", "text": "How would you test a function that calls an external API?", "difficulty": "medium", "expects": ["mocking", "side effects"]},
                {"id": "ts-h1", "text": "How would you make a flaky test reliable?", "difficulty": "hard", "expects": ["flakiness", "ci"]},
            ],
        },
        {
            "id": "topic-algorithms",
            "title": "Algorithms & Data Structures",
            "description": "Core algorithmic techniques.",
            "questions": [
                {"id": "al-m1", "text": "Explain the time complexity of a binary search.", "difficulty": "medium", "expects": ["logarithmic", "sorted input"]},
                {"id": "al-h1", "text": "Design an algorithm to find the most frequent element in a list.", "difficulty": "hard", "expects": ["hashmap", "counting"]},
            ],
        },
    ],
}


def _write_curriculum(tmp_path: Path, payload: object) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "curriculum.json").write_text(json.dumps(payload), encoding="utf-8")
    return data_dir


def _candidate() -> CandidateProfile:
    return CandidateProfile(
        id="candidate-001",
        name="Alex Rivera",
        role="Backend Engineer",
        years_of_experience=2.0,
        skills=[SkillLevel(name="Python", level="intermediate")],
        learning_journey=[],
        preferred_languages=["Python"],
        focus_areas=["Databases"],
        notes="",
    )


def _mock_gemini(result: dict | None = None, error: Exception | None = None) -> mock.MagicMock:
    gemini = mock.MagicMock()
    gemini.enabled = True
    if error is not None:
        gemini.generate_json.side_effect = error
    else:
        gemini.generate_json.return_value = result
    return gemini


def _build_stack(tmp_path: Path, gemini) -> SimpleNamespace:
    """Wire a full engine stack whose FollowUpAdvisor uses ``gemini``."""
    data_dir = _write_curriculum(tmp_path, SYNTHETIC_CURRICULUM)
    db = Database(tmp_path / "interview.db")
    db.initialize()

    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    score_repo = ScoreRepository(db)
    feedback_repo = FeedbackRepository(db)
    session_manager = SessionManager(session_repo)
    memory_engine = MemoryEngine(
        conversation_memory=ConversationMemory(),
        gemini_service=gemini,
        session_repository=session_repo,
        message_repository=message_repo,
        score_repository=score_repo,
        feedback_repository=feedback_repo,
    )
    curriculum_loader = CurriculumLoader(data_dir=data_dir)
    candidate_analyzer = CandidateAnalyzer(data_dir=data_dir)
    planner = QuestionPlanner(
        curriculum_loader=curriculum_loader,
        candidate_analyzer=candidate_analyzer,
        memory_engine=memory_engine,
    )
    evaluation_engine = EvaluationEngine(
        gemini_service=gemini,
        score_repository=score_repo,
        message_repository=message_repo,
    )
    feedback_generator = FeedbackGenerator(
        evaluation_engine=evaluation_engine,
        score_repository=score_repo,
        feedback_repository=feedback_repo,
        gemini_service=gemini,
        session_repository=session_repo,
    )
    prompt_builder = PromptBuilder()
    advisor = FollowUpAdvisor(prompt_builder=prompt_builder, gemini_service=gemini)
    engine = InterviewEngine(
        session_manager,
        planner,
        evaluation_engine,
        memory_engine,
        curriculum_loader=curriculum_loader,
        candidate_analyzer=candidate_analyzer,
        feedback_generator=feedback_generator,
        message_repository=message_repo,
        follow_up_advisor=advisor,
    )
    return SimpleNamespace(
        engine=engine,
        advisor=advisor,
        prompt_builder=prompt_builder,
        session_manager=session_manager,
        message_repo=message_repo,
        score_repo=score_repo,
        feedback_repo=feedback_repo,
    )


def _questions(stack: SimpleNamespace, session_id: str) -> list[dict]:
    return stack.session_manager.get_session(session_id).context["plan"]["questions"]


def _context(stack: SimpleNamespace, session_id: str) -> dict:
    return stack.session_manager.get_session(session_id).context


def _current(stack: SimpleNamespace, session_id: str) -> dict:
    return _context(stack, session_id)["current"]


def _full_answer(question: dict) -> str:
    return "I can explain this. " + ", ".join(question["expects"]) + " are all important concepts."


def _weak_answer(_question: dict) -> str:
    return "I'm not sure about this one."


def _base_decision(**overrides) -> dict:
    payload = {
        "should_follow_up": True,
        "reason": "probe depth",
        "question": "Can you elaborate on how immutability affects your design?",
        "target_concept": "immutable",
    }
    payload.update(overrides)
    return payload


# --- PromptBuilder -----------------------------------------------------------


@pytest.fixture()
def stack(tmp_path: Path) -> SimpleNamespace:
    """The standard wired stack with a Gemini that requests follow-ups."""
    return _build_stack(tmp_path, _mock_gemini(_base_decision()))


class TestPromptBuilder:
    def test_prompt_contains_curriculum_context(self, stack: SimpleNamespace) -> None:
        prompt = self._build_prompt(stack)
        assert "Python Fundamentals" in prompt
        assert "topic-python" in prompt
        assert "Explain the difference between a list and a tuple." in prompt
        assert "immutable, mutable" in prompt

    def test_prompt_contains_candidate_answer(self, stack: SimpleNamespace) -> None:
        prompt = self._build_prompt(stack)
        assert "I think tuples cannot change." in prompt

    def test_prompt_contains_evaluation_and_missing_concepts(self, stack: SimpleNamespace) -> None:
        prompt = self._build_prompt(stack)
        assert "score: 5.0/10" in prompt
        assert "mutable" in prompt
        assert "missing concepts" in prompt

    def test_prompt_instructs_single_follow_up(self, stack: SimpleNamespace) -> None:
        prompt = self._build_prompt(stack)
        assert "at most ONE follow-up" in prompt
        assert "target_concept" in prompt

    def test_prompt_includes_recent_conversation(self, stack: SimpleNamespace) -> None:
        prompt = self._build_prompt(stack)
        assert "interviewer: Let's begin." in prompt
        assert "candidate: I think tuples cannot change." in prompt

    def test_load_template_missing_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            PromptBuilder().load_template("does_not_exist")

    @staticmethod
    def _build_prompt(stack: SimpleNamespace) -> str:
        return stack.prompt_builder.build_follow_up_prompt(
            session_id="sess-prompt",
            topic={
                "id": "topic-python",
                "title": "Python Fundamentals",
                "description": "Data structures.",
            },
            question={
                "curriculum_question_id": "py-e1",
                "topic_id": "topic-python",
                "text": "Explain the difference between a list and a tuple.",
                "difficulty": "easy",
                "expects": ["immutable", "mutable"],
            },
            answer="I think tuples cannot change.",
            evaluation={"score": 5.0, "missing": ["mutable"], "covered": ["immutable"]},
            conversation_context=[
                {"role": "interviewer", "content": "Let's begin."},
                {"role": "candidate", "content": "I think tuples cannot change."},
            ],
        )


# --- FollowUpAdvisor ---------------------------------------------------------


class TestFollowUpAdvisor:
    def test_gemini_requests_a_follow_up(self) -> None:
        advisor = FollowUpAdvisor(PromptBuilder(), _mock_gemini(_base_decision()))
        decision = advisor.decide(**_kwargs())
        assert decision.should_follow_up is True
        assert decision.question == _base_decision()["question"]
        assert decision.target_concept == "immutable"
        assert decision.source == AI_SOURCE

    def test_gemini_declines_a_follow_up(self) -> None:
        advisor = FollowUpAdvisor(
            PromptBuilder(),
            _mock_gemini({"should_follow_up": False, "reason": "clear", "question": "", "target_concept": ""}),
        )
        decision = advisor.decide(**_kwargs())
        assert decision.should_follow_up is False
        assert decision.question == ""
        assert decision.target_concept is None
        assert decision.source == AI_SOURCE

    def test_follow_up_is_grounded_in_expects(self) -> None:
        advisor = FollowUpAdvisor(PromptBuilder(), _mock_gemini(_base_decision()))
        decision = advisor.decide(**_kwargs())
        assert decision.target_concept in ["immutable", "mutable"]

    def test_unknown_target_concept_falls_back_to_deterministic(self) -> None:
        advisor = FollowUpAdvisor(
            PromptBuilder(),
            _mock_gemini(_base_decision(target_concept="quantum entanglement")),
        )
        decision = advisor.decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE
        assert decision.should_follow_up is True
        assert decision.target_concept in ["immutable", "mutable"]

    def test_missing_question_text_falls_back(self) -> None:
        advisor = FollowUpAdvisor(
            PromptBuilder(),
            _mock_gemini(_base_decision(question="  ")),
        )
        decision = advisor.decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE

    def test_llm_error_falls_back_to_deterministic(self) -> None:
        advisor = FollowUpAdvisor(PromptBuilder(), _mock_gemini(error=LLMError("boom")))
        decision = advisor.decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE
        assert decision.should_follow_up is True
        assert decision.target_concept == "immutable"

    def test_unavailable_falls_back_without_calling_gemini(self) -> None:
        gemini = _mock_gemini(_base_decision())
        gemini.enabled = False
        advisor = FollowUpAdvisor(PromptBuilder(), gemini)
        decision = advisor.decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE
        gemini.generate_json.assert_not_called()

    def test_unexpected_exception_falls_back(self) -> None:
        advisor = FollowUpAdvisor(PromptBuilder(), _mock_gemini(error=RuntimeError("kaboom")))
        decision = advisor.decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE

    def test_schema_is_applied_to_generate_json_call(self) -> None:
        gemini = _mock_gemini(_base_decision())
        advisor = FollowUpAdvisor(PromptBuilder(), gemini)
        advisor.decide(**_kwargs())
        args, _ = gemini.generate_json.call_args
        assert args[0].startswith("You are a senior technical interviewer")
        assert args[1] == FOLLOW_UP_SCHEMA


def _kwargs() -> dict:
    return dict(
        session_id="sess-advisor",
        topic={"id": "topic-python", "title": "Python Fundamentals", "description": "Data structures."},
        question={
            "curriculum_question_id": "py-e1",
            "topic_id": "topic-python",
            "text": "Explain the difference between a list and a tuple.",
            "difficulty": "easy",
            "expects": ["immutable", "mutable"],
            "follow_up_allowed": True,
        },
        answer="I'm not sure about this one.",
        evaluation={"score": 0.0, "missing": ["immutable", "mutable"], "covered": []},
        conversation_context=[],
    )


# --- InterviewEngine integration ---------------------------------------------


class TestEngineIntegration:
    def test_gemini_requests_a_follow_up(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, _mock_gemini(_base_decision()))
        stack.engine.start("sess-ai", _candidate())
        questions = _questions(stack, "sess-ai")
        resp = stack.engine.handle_answer("sess-ai", _weak_answer(questions[0]))

        assert resp.done is False
        assert resp.reply == _base_decision()["question"]
        session = stack.session_manager.get_session("sess-ai")
        assert InterviewState(session.state) == InterviewState.FOLLOW_UP
        context = session.context
        assert context["phase"] == "follow_up"
        assert context["pending_follow_up"] == "immutable"
        assert context["follow_ups"][0]["source"] == AI_SOURCE
        assert context["follow_ups"][0]["target_concept"] == "immutable"

        follow_up_message = [
            m for m in stack.message_repo.list_by_session("sess-ai")
            if m["metadata"].get("kind") == "follow_up"
        ][0]
        assert follow_up_message["metadata"]["follow_up"]["source"] == AI_SOURCE
        assert follow_up_message["metadata"]["follow_up"]["target_concept"] == "immutable"

    def test_gemini_declines_a_follow_up(self, tmp_path: Path) -> None:
        stack = _build_stack(
            tmp_path,
            _mock_gemini({"should_follow_up": False, "reason": "answer was sufficient", "question": "", "target_concept": ""}),
        )
        stack.engine.start("sess-no", _candidate())
        questions = _questions(stack, "sess-no")
        resp = stack.engine.handle_answer("sess-no", _weak_answer(questions[0]))

        assert resp.reply == questions[1]["text"]
        context = _context(stack, "sess-no")
        assert context["phase"] == "question"
        assert context["follow_up_count"] == 0
        assert context["follow_ups"] == []
        assert InterviewState(stack.session_manager.get_session("sess-no").state) == InterviewState.QUESTION

    def test_follow_up_is_only_one_then_next_primary(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, _mock_gemini(_base_decision()))
        stack.engine.start("sess-one", _candidate())
        questions = _questions(stack, "sess-one")
        stack.engine.handle_answer("sess-one", _weak_answer(questions[0]))
        resp = stack.engine.handle_answer("sess-one", _full_answer(questions[0]))

        assert resp.reply == questions[1]["text"]
        context = _context(stack, "sess-one")
        assert context["phase"] == "question"
        assert context["pending_follow_up"] is None

    def test_follow_up_does_not_increment_primary_count(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, _mock_gemini(_base_decision()))
        stack.engine.start("sess-count", _candidate())
        questions = _questions(stack, "sess-count")
        stack.engine.handle_answer("sess-count", _weak_answer(questions[0]))
        stack.engine.handle_answer("sess-count", _full_answer(questions[0]))

        context = _context(stack, "sess-count")
        assert context["primary_question_count"] == 1
        assert context["primary_answered"] == 2
        assert context["follow_up_count"] == 1

    def test_follow_up_answer_is_persisted(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, _mock_gemini(_base_decision()))
        stack.engine.start("sess-persist", _candidate())
        questions = _questions(stack, "sess-persist")
        stack.engine.handle_answer("sess-persist", _weak_answer(questions[0]))
        stack.engine.handle_answer("sess-persist", "Right, tuples cannot be changed after creation.")

        context = _context(stack, "sess-persist")
        assert len(context["answers"]) == 2
        assert context["answers"][1]["answer"] == "Right, tuples cannot be changed after creation."
        assert [e["kind"] for e in context["evaluations"]] == ["primary", "follow_up"]

        messages = stack.message_repo.list_by_session("sess-persist")
        assert len([m for m in messages if m["role"] == "candidate"]) == 2
        assert len([m for m in messages if m["metadata"].get("kind") == "follow_up"]) == 1

        assert len(stack.score_repo.list_by_session("sess-persist")) == 2

    def test_gemini_failure_falls_back_to_deterministic_follow_up(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, _mock_gemini(error=LLMError("rate limited")))
        stack.engine.start("sess-fail", _candidate())
        questions = _questions(stack, "sess-fail")
        resp = stack.engine.handle_answer("sess-fail", _weak_answer(questions[0]))

        assert resp.done is False
        assert questions[0]["expects"][0] in resp.reply
        context = _context(stack, "sess-fail")
        assert context["phase"] == "follow_up"
        assert context["pending_follow_up"] == questions[0]["expects"][0]
        assert context["follow_ups"][0]["source"] == DETERMINISTIC_SOURCE

    def test_gemini_unavailable_falls_back_to_deterministic(self, tmp_path: Path) -> None:
        gemini = GeminiService(settings=Settings(gemini_enabled=False))
        stack = _build_stack(tmp_path, gemini)
        stack.engine.start("sess-unavail", _candidate())
        questions = _questions(stack, "sess-unavail")
        resp = stack.engine.handle_answer("sess-unavail", _weak_answer(questions[0]))

        assert questions[0]["expects"][0] in resp.reply
        context = _context(stack, "sess-unavail")
        assert context["follow_ups"][0]["source"] == DETERMINISTIC_SOURCE
        assert context["phase"] == "follow_up"

    def test_malformed_gemini_json_falls_back_to_deterministic(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, _mock_gemini(error=ValidationError("Gemini returned malformed JSON.")))
        stack.engine.start("sess-mal", _candidate())
        questions = _questions(stack, "sess-mal")
        resp = stack.engine.handle_answer("sess-mal", _weak_answer(questions[0]))

        assert questions[0]["expects"][0] in resp.reply
        context = _context(stack, "sess-mal")
        assert context["follow_ups"][0]["source"] == DETERMINISTIC_SOURCE

    def test_unknown_concept_from_gemini_falls_back(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, _mock_gemini(_base_decision(target_concept="quantum")))
        stack.engine.start("sess-unk", _candidate())
        questions = _questions(stack, "sess-unk")
        stack.engine.handle_answer("sess-unk", _weak_answer(questions[0]))

        context = _context(stack, "sess-unk")
        assert context["follow_ups"][0]["source"] == DETERMINISTIC_SOURCE
        assert context["follow_ups"][0]["target_concept"] in questions[0]["expects"]

    def test_complete_interview_reaches_done_with_ai_follow_ups(self, tmp_path: Path) -> None:
        def respond(_question: dict) -> str:
            return "I'm not sure about this one."

        gemini = mock.MagicMock()
        gemini.enabled = True
        gemini.generate_json.return_value = _base_decision()
        stack = _build_stack(tmp_path, gemini)

        stack.engine.start("sess-done", _candidate())
        resp = None
        for _ in range(30):
            resp = stack.engine.handle_answer("sess-done", respond(_current(stack, "sess-done")))
            if resp.done:
                break

        assert resp is not None and resp.done is True
        assert resp.feedback is not None
        context = _context(stack, "sess-done")
        assert context["primary_question_count"] == 8
        assert context["follow_up_count"] >= 1
        assert context["primary_answered"] == 8 + context["follow_up_count"]
        assert InterviewState(stack.session_manager.get_session("sess-done").state) == InterviewState.COMPLETED
