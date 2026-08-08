"""Focused tests for AI-generated final feedback reports.

Covers the PromptBuilder feedback prompt, the FeedbackGenerator AI-first path
with deterministic fallbacks, and the InterviewEngine integration. Gemini is
fully mocked — no real API calls are made. The deterministic path is exercised
by the existing ``test_interview_engine`` suite; these tests add the AI layer.
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
from app.models.common import utc_now
from app.models.session import SessionCreate
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import (
    AI_SOURCE,
    DETERMINISTIC_SOURCE,
    NEXT_STEP_PREFIX,
    FeedbackGenerator,
)
from app.services.gemini_service import GeminiService
from app.services.interview_engine import InterviewEngine
from app.services.memory_engine import MemoryEngine
from app.services.prompt_builder import FEEDBACK_SCHEMA, PromptBuilder
from app.services.question_planner import QuestionPlanner
from app.services.session_manager import SessionManager
from app.utils.config import Settings
from app.utils.errors import LLMError, ValidationError

#: Synthetic 5-topic curriculum with 14 grounded questions (8-primary plans).
SYNTHETIC_CURRICULUM = {
    "id": "curriculum-001",
    "title": "Synthetic Interview Curriculum",
    "description": "Five topics with varied-difficulty questions for feedback tests.",
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
    if isinstance(payload, Path):
        shutil.copy(payload, data_dir / "curriculum.json")
    else:
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


def _analysis() -> dict:
    """Candidate analysis dump matching the seeded session context."""
    return {
        "candidate_id": "candidate-001",
        "profile": {
            "id": "candidate-001",
            "name": "Alex Rivera",
            "role": "Backend Engineer",
            "years_of_experience": 2.0,
            "skills": [{"name": "Python", "level": "intermediate"}],
            "learning_journey": [],
            "preferred_languages": ["Python"],
            "focus_areas": ["Databases"],
            "notes": "",
        },
        "completed_topics": [],
        "skipped_topics": [],
        "attempts": {},
        "learning_signals": ["preferred language: Python", "focus area: Databases"],
        "strengths": ["Python (intermediate)"],
        "areas_for_further_assessment": [],
    }


def _seed_context() -> dict:
    """Session context with two grounded evaluations (one strong, one weak)."""
    return {
        "candidate_id": "candidate-001",
        "curriculum_id": "curriculum-001",
        "plan": {"total_questions": 2, "questions": []},
        "analysis": _analysis(),
        "topics": [
            {
                "id": "topic-python",
                "title": "Python Fundamentals",
                "description": "Data structures.",
                "questions": [],
            },
            {
                "id": "topic-databases",
                "title": "Databases & SQL",
                "description": "Relational modeling.",
                "questions": [],
            },
        ],
        "asked_questions": [
            {
                "curriculum_question_id": "py-e1",
                "topic_id": "topic-python",
                "text": "Explain the difference between a list and a tuple.",
                "difficulty": "easy",
                "expects": ["immutable", "mutable"],
            },
            {
                "curriculum_question_id": "db-e1",
                "topic_id": "topic-databases",
                "text": "Explain the differences between a primary key and a foreign key.",
                "difficulty": "easy",
                "expects": ["unique", "relationship"],
            },
        ],
        "answers": [
            {
                "question_id": "py-e1",
                "topic_id": "topic-python",
                "answer": "Tuples are immutable while lists are mutable.",
                "score": 10.0,
            },
            {
                "question_id": "db-e1",
                "topic_id": "topic-databases",
                "answer": "I am not sure about keys.",
                "score": 0.0,
            },
        ],
        "evaluations": [
            {
                "question_id": "py-e1",
                "topic_id": "topic-python",
                "kind": "primary",
                "score": 10.0,
                "covered": ["immutable", "mutable"],
                "missing": [],
            },
            {
                "question_id": "db-e1",
                "topic_id": "topic-databases",
                "kind": "primary",
                "score": 0.0,
                "covered": [],
                "missing": ["unique", "relationship"],
            },
        ],
        "primary_index": 1,
        "phase": "question",
        "current": {},
        "pending_follow_up": None,
        "primary_question_count": 2,
        "follow_up_count": 0,
        "primary_answered": 2,
        "topics_covered": ["topic-python", "topic-databases"],
    }


def _mock_gemini(result: dict | None = None, error: Exception | None = None) -> mock.MagicMock:
    gemini = mock.MagicMock()
    gemini.enabled = True
    if error is not None:
        gemini.generate_json.side_effect = error
    else:
        gemini.generate_json.return_value = result
    return gemini


def _build_generator(tmp_path: Path, gemini) -> SimpleNamespace:
    """Wire a FeedbackGenerator (with PromptBuilder) against a seeded session."""
    db = Database(tmp_path / "feedback.db")
    db.initialize()

    session_repo = SessionRepository(db)
    score_repo = ScoreRepository(db)
    feedback_repo = FeedbackRepository(db)
    session_manager = SessionManager(session_repo)
    session_manager.create_session(
        SessionCreate(candidate_id="candidate-001", curriculum_id="curriculum-001"),
        session_id="sess-fb",
    )
    session_manager.update_context("sess-fb", _seed_context())
    now = utc_now()
    score_repo.create(
        score_id="s1",
        session_id="sess-fb",
        topic_id="topic-python",
        question_id="py-e1",
        score=10.0,
        rationale="",
        created_at=now,
    )
    score_repo.create(
        score_id="s2",
        session_id="sess-fb",
        topic_id="topic-databases",
        question_id="db-e1",
        score=0.0,
        rationale="",
        created_at=now,
    )

    generator = FeedbackGenerator(
        evaluation_engine=mock.MagicMock(),
        score_repository=score_repo,
        feedback_repository=feedback_repo,
        gemini_service=gemini,
        session_repository=session_repo,
        prompt_builder=PromptBuilder(),
    )
    return SimpleNamespace(
        generator=generator,
        session_manager=session_manager,
        score_repo=score_repo,
        feedback_repo=feedback_repo,
    )


def _build_engine_stack(tmp_path: Path, gemini) -> SimpleNamespace:
    """Wire a full engine stack whose FeedbackGenerator uses ``gemini``."""
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
        prompt_builder=PromptBuilder(),
    )
    engine = InterviewEngine(
        session_manager,
        planner,
        evaluation_engine,
        memory_engine,
        curriculum_loader=curriculum_loader,
        candidate_analyzer=candidate_analyzer,
        feedback_generator=feedback_generator,
        message_repository=message_repo,
    )
    return SimpleNamespace(
        engine=engine,
        session_manager=session_manager,
        message_repo=message_repo,
        score_repo=score_repo,
        feedback_repo=feedback_repo,
    )


def _feedback_payload(**overrides) -> dict:
    payload = {
        "overall_summary": "Strong fundamentals, but relational modeling needs practice.",
        "strengths": ["Clear understanding of Python data structures."],
        "improvement_areas": ["Relational modeling concepts such as primary and foreign keys."],
        "next_steps": ["Practice designing a relational schema."],
    }
    payload.update(overrides)
    return payload


# --- PromptBuilder -----------------------------------------------------------


class TestPromptBuilder:
    def _context(self) -> dict:
        return {
            "candidate": _analysis(),
            "topic_summaries": [
                {"topic_id": "topic-python", "title": "Python Fundamentals", "average_score": 10.0},
                {"topic_id": "topic-databases", "title": "Databases & SQL", "average_score": 0.0},
            ],
            "overall_score": 5.0,
            "evaluations": [
                {
                    "question_id": "py-e1",
                    "topic_id": "topic-python",
                    "kind": "primary",
                    "question": "Explain the difference between a list and a tuple.",
                    "answer": "Tuples are immutable while lists are mutable.",
                    "score": 10.0,
                    "covered": ["immutable", "mutable"],
                    "missing": [],
                },
                {
                    "question_id": "db-e1",
                    "topic_id": "topic-databases",
                    "kind": "primary",
                    "question": "Explain the differences between a primary key and a foreign key.",
                    "answer": "I am not sure about keys.",
                    "score": 0.0,
                    "covered": [],
                    "missing": ["unique", "relationship"],
                },
            ],
        }

    def _build_prompt(self) -> str:
        return PromptBuilder().build_feedback_prompt("sess-prompt", context=self._context())

    def test_prompt_contains_candidate_profile(self) -> None:
        prompt = self._build_prompt()
        assert "Alex Rivera" in prompt
        assert "Backend Engineer" in prompt
        assert "Python (intermediate)" in prompt

    def test_prompt_contains_topic_performance_and_overall_score(self) -> None:
        prompt = self._build_prompt()
        assert "Python Fundamentals" in prompt
        assert "average score 10.0/10" in prompt
        assert "OVERALL SCORE: 5.0/10" in prompt

    def test_prompt_contains_qa_with_matched_and_missing_concepts(self) -> None:
        prompt = self._build_prompt()
        assert "Explain the difference between a list and a tuple." in prompt
        assert "Tuples are immutable while lists are mutable." in prompt
        assert "covered concepts: immutable, mutable" in prompt
        assert "missing concepts: unique, relationship" in prompt

    def test_prompt_instructs_grounding_and_anti_invention(self) -> None:
        prompt = self._build_prompt()
        assert "Use ONLY the supplied curriculum context" in prompt
        assert "Do NOT invent" in prompt
        assert "overall_summary" in prompt
        assert "next_steps" in prompt

    def test_schema_is_applied_to_generate_json_call(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(_feedback_payload())
        stack = _build_generator(tmp_path, gemini)
        stack.generator.generate_report("sess-fb")
        args, _ = gemini.generate_json.call_args
        assert args[0].startswith("You are a senior technical interviewer")
        assert args[1] == FEEDBACK_SCHEMA


# --- FeedbackGenerator: AI-first ---------------------------------------------


class TestFeedbackGenerator:
    def test_ai_payload_is_used_when_gemini_enabled(self, tmp_path: Path) -> None:
        stack = _build_generator(tmp_path, _mock_gemini(_feedback_payload()))
        report = stack.generator.generate_report("sess-fb")

        assert report.summary == _feedback_payload()["overall_summary"]
        assert report.strengths == _feedback_payload()["strengths"]
        assert report.improvements == _feedback_payload()["improvement_areas"] + [
            f"{NEXT_STEP_PREFIX}{_feedback_payload()['next_steps'][0]}"
        ]
        assert report.source == AI_SOURCE

        row = stack.feedback_repo.get_by_session("sess-fb")
        assert row is not None
        assert row["source"] == AI_SOURCE
        assert row["summary"] == _feedback_payload()["overall_summary"]

    def test_ai_payload_fields_are_normalized(self, tmp_path: Path) -> None:
        stack = _build_generator(
            tmp_path,
            _mock_gemini(
                _feedback_payload(
                    overall_summary="   padded summary   ",
                    strengths=["  solid   ", " ", "clear"],
                    improvement_areas=[""],
                    next_steps=[" practice more ", 123],
                )
            ),
        )
        report = stack.generator.generate_report("sess-fb")
        assert report.summary == "padded summary"
        assert report.strengths == ["solid", "clear"]
        assert report.improvements == [f"{NEXT_STEP_PREFIX}practice more", f"{NEXT_STEP_PREFIX}123"]

    def test_ai_payload_does_not_change_overall_score(self, tmp_path: Path) -> None:
        stack = _build_generator(tmp_path, _mock_gemini(_feedback_payload()))
        report = stack.generator.generate_report("sess-fb")
        assert report.overall_score == 5.0
        row = stack.feedback_repo.get_by_session("sess-fb")
        assert row["overall_score"] == 5.0


# --- FeedbackGenerator: deterministic fallbacks -------------------------------


class TestDeterministicFallback:
    def test_deterministic_when_gemini_disabled(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(_feedback_payload())
        gemini.enabled = False
        stack = _build_generator(tmp_path, gemini)
        report = stack.generator.generate_report("sess-fb")

        assert report.source == DETERMINISTIC_SOURCE
        assert report.summary == (
            "Interview complete: 2 answer(s) across 2 topic(s) with an overall score of 5.0/10."
        )
        assert report.strengths == ["Python Fundamentals (10.0/10)"]
        assert report.improvements == ["Databases & SQL (0.0/10)", "Review: unique", "Review: relationship"]
        gemini.generate_json.assert_not_called()

    def test_deterministic_on_llm_error(self, tmp_path: Path) -> None:
        stack = _build_generator(tmp_path, _mock_gemini(error=LLMError("rate limited")))
        report = stack.generator.generate_report("sess-fb")
        assert report.source == DETERMINISTIC_SOURCE
        assert report.summary.startswith("Interview complete: 2 answer(s)")

    def test_deterministic_on_malformed_json(self, tmp_path: Path) -> None:
        stack = _build_generator(
            tmp_path,
            _mock_gemini(error=ValidationError("Gemini returned malformed JSON.")),
        )
        report = stack.generator.generate_report("sess-fb")
        assert report.source == DETERMINISTIC_SOURCE
        assert report.summary.startswith("Interview complete: 2 answer(s)")

    def test_deterministic_on_empty_payload(self, tmp_path: Path) -> None:
        stack = _build_generator(tmp_path, _mock_gemini({}))
        report = stack.generator.generate_report("sess-fb")
        assert report.source == DETERMINISTIC_SOURCE

    def test_deterministic_on_blank_payload(self, tmp_path: Path) -> None:
        stack = _build_generator(
            tmp_path,
            _mock_gemini(
                _feedback_payload(
                    overall_summary="   ",
                    strengths=[],
                    improvement_areas=[],
                    next_steps=[],
                )
            ),
        )
        report = stack.generator.generate_report("sess-fb")
        assert report.source == DETERMINISTIC_SOURCE
        assert report.summary.startswith("Interview complete: 2 answer(s)")

    def test_deterministic_on_unexpected_exception(self, tmp_path: Path) -> None:
        stack = _build_generator(tmp_path, _mock_gemini(error=RuntimeError("kaboom")))
        report = stack.generator.generate_report("sess-fb")
        assert report.source == DETERMINISTIC_SOURCE

    def test_no_ai_when_no_scored_answers(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(_feedback_payload())
        stack = _build_generator(tmp_path, gemini)
        for score_id in ("s1", "s2"):
            stack.score_repo.delete_by_id(score_id)
        report = stack.generator.generate_report("sess-fb")
        assert report.source == DETERMINISTIC_SOURCE
        assert report.overall_score == 0.0
        gemini.generate_json.assert_not_called()

    def test_no_ai_without_prompt_builder(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(_feedback_payload())
        db = Database(tmp_path / "no-builder.db")
        db.initialize()
        generator = FeedbackGenerator(
            evaluation_engine=mock.MagicMock(),
            score_repository=ScoreRepository(db),
            feedback_repository=FeedbackRepository(db),
            gemini_service=gemini,
            session_repository=SessionRepository(db),
            prompt_builder=None,
        )
        session_manager = SessionManager(SessionRepository(db))
        session_manager.create_session(
            SessionCreate(candidate_id="candidate-001", curriculum_id="curriculum-001"),
            session_id="sess-fb",
        )
        session_manager.update_context("sess-fb", _seed_context())
        with db.connection() as conn:
            conn.execute(
                "INSERT INTO scores (id, session_id, topic_id, question_id, score, rationale, created_at) "
                "VALUES ('s1', 'sess-fb', 'topic-python', 'py-e1', 10.0, '', ?)",
                (utc_now().isoformat(),),
            )
        report = generator.generate_report("sess-fb")
        assert report.source == DETERMINISTIC_SOURCE
        gemini.generate_json.assert_not_called()


# --- InterviewEngine integration ---------------------------------------------


def _full_answer(question: dict) -> str:
    return "I can explain this. " + ", ".join(question["expects"]) + " are all important concepts."


def _weak_answer(_question: dict) -> str:
    return "I'm not sure about this one."


def _current(stack: SimpleNamespace, session_id: str) -> dict:
    return stack.session_manager.get_session(session_id).context["current"]


def _drive_to_done(stack: SimpleNamespace, responder, session_id: str = "sess-001"):
    resp = stack.engine.start(session_id, _candidate())
    while not resp.done:
        resp = stack.engine.handle_answer(session_id, responder(_current(stack, session_id)))
    return resp


class TestEngineIntegration:
    def test_ai_next_steps_surface_in_response_next(self, tmp_path: Path) -> None:
        gemini = mock.MagicMock()
        gemini.enabled = True

        def side_effect(prompt: str, schema: dict) -> dict:
            if "QUESTION-BY-QUESTION EVALUATIONS" in prompt:
                return _feedback_payload()
            return {
                "should_follow_up": False,
                "reason": "answer was sufficient",
                "question": "",
                "target_concept": "",
            }

        gemini.generate_json.side_effect = side_effect
        stack = _build_engine_stack(tmp_path, gemini)
        resp = _drive_to_done(stack, _weak_answer)

        assert resp.done is True
        assert resp.feedback is not None
        assert _feedback_payload()["next_steps"][0] in resp.feedback.next
        assert not any(item.startswith(NEXT_STEP_PREFIX) for item in resp.feedback.gaps)
        assert _feedback_payload()["overall_summary"] == resp.feedback.summary

        row = stack.feedback_repo.get_by_session("sess-001")
        assert row is not None
        assert row["source"] == AI_SOURCE

    def test_deterministic_report_is_byte_identical(self, tmp_path: Path) -> None:
        gemini = GeminiService(settings=Settings(gemini_enabled=False))
        stack = _build_engine_stack(tmp_path, gemini)
        resp = _drive_to_done(stack, _full_answer)

        assert resp.done is True
        assert resp.feedback is not None
        row = stack.feedback_repo.get_by_session("sess-001")
        assert row is not None
        assert row["source"] == DETERMINISTIC_SOURCE
        assert row["overall_score"] == 10.0
        assert row["summary"] == (
            "Interview complete: 8 answer(s) across 5 topic(s) with an overall score of 10.0/10."
        )
        assert not any(item.startswith(NEXT_STEP_PREFIX) for item in row["improvements"])
