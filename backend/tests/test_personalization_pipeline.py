"""Personalization-pipeline regression tests.

Proves the interview is genuinely personalized end to end: the exact candidate
object sent by the frontend reaches the backend, CandidateAnalyzer produces
candidate-specific analysis, QuestionPlanner receives that analysis, topic
ranking is candidate-dependent, the first question comes from the generated
candidate-specific plan, plans are deterministic for a fixed candidate, and
distinct sessions stay isolated.

Uses a synthetic 5-topic curriculum (id ``curriculum-001``) with 14 grounded
questions, matching the engine's default curriculum id, so plans are built in
production mode (8 questions / 4 topics) and personalization is expressed in
both the ordering and the selected subset.

Run with ``-s`` to see the per-candidate debug report in
``TestPersonalizationDebugLogging`` (candidate A vs candidate B selected
topics/questions).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database.connection import Database
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.memory.conversation_memory import ConversationMemory
from app.models.candidate import CandidateProfile, SkillLevel
from app.models.curriculum import Curriculum
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator
from app.services.gemini_service import GeminiService
from app.services.interview_engine import InterviewEngine
from app.services.memory_engine import MemoryEngine
from app.services.question_planner import QuestionPlanner
from app.services.session_manager import SessionManager
from app.utils.config import Settings

#: Synthetic 5-topic curriculum with 14 grounded questions across all tiers.
SYNTHETIC_CURRICULUM = {
    "id": "curriculum-001",
    "title": "Synthetic Interview Curriculum",
    "description": "Five topics with varied-difficulty questions for personalization tests.",
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
    """Write ``payload`` as curriculum.json in a temp data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "curriculum.json").write_text(json.dumps(payload), encoding="utf-8")
    return data_dir


def _candidate_a() -> CandidateProfile:
    """Candidate who leans toward System Design + Python."""
    return CandidateProfile(
        id="candidate-a",
        name="Ada Systems",
        role="Backend Engineer",
        years_of_experience=2.0,
        skills=[
            SkillLevel(name="Python", level="advanced"),
            SkillLevel(name="System Design", level="beginner"),
        ],
        learning_journey=[
            {"type": "course", "title": "Python for Everybody", "description": "Intro Python."}
        ],
        preferred_languages=["Python"],
        focus_areas=["System design", "Backend API design"],
        notes="learning distributed systems next.",
    )


def _candidate_b() -> CandidateProfile:
    """Candidate who leans toward Databases & SQL + Software Testing."""
    return CandidateProfile(
        id="candidate-b",
        name="Bea Query",
        role="Backend Engineer",
        years_of_experience=3.0,
        skills=[
            SkillLevel(name="SQL", level="intermediate"),
            SkillLevel(name="Python", level="advanced"),
        ],
        learning_journey=[
            {"type": "project", "title": "B-tree Indexing", "description": "Built a small index toy."}
        ],
        preferred_languages=["SQL"],
        focus_areas=["Databases", "Software Testing"],
        notes="learning advanced SQL and database indexing next.",
    )


def _build_stack(tmp_path: Path) -> SimpleNamespace:
    """Wire every engine collaborator against a temp curriculum + temp DB."""
    data_dir = _write_curriculum(tmp_path, SYNTHETIC_CURRICULUM)
    db = Database(tmp_path / "interview.db")
    db.initialize()

    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    score_repo = ScoreRepository(db)
    feedback_repo = FeedbackRepository(db)
    session_manager = SessionManager(session_repo)
    gemini = GeminiService(settings=Settings(gemini_enabled=False))
    memory_engine = MemoryEngine(conversation_memory=ConversationMemory(), gemini_service=gemini)
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
        planner=planner,
        candidate_analyzer=candidate_analyzer,
        curriculum=Curriculum(**SYNTHETIC_CURRICULUM),
    )


@pytest.fixture()
def stack(tmp_path: Path) -> SimpleNamespace:
    """The standard wired interview stack."""
    return _build_stack(tmp_path)


@pytest.fixture()
def client(stack: SimpleNamespace):
    """A TestClient bound to the wired engine (skipped when httpx is absent)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_interview_engine
    from app.api.middleware import setup_error_handlers
    from app.api.routes.interview import router

    pytest.importorskip("httpx")
    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_interview_engine] = lambda: stack.engine
    return TestClient(app)


# --- Helpers ----------------------------------------------------------------


def _questions(stack: SimpleNamespace, session_id: str) -> list[dict]:
    """The planned questions for a session, in ask order."""
    return stack.session_manager.get_session(session_id).context["plan"]["questions"]


def _context(stack: SimpleNamespace, session_id: str) -> dict:
    return stack.session_manager.get_session(session_id).context


def _full_answer(question: dict) -> str:
    """An answer that covers every expected concept of ``question``."""
    return "I can explain this. " + ", ".join(question["expects"]) + " are all important concepts."


# --- 1. Candidate reaches the backend ---------------------------------------


class TestCandidateReachesBackend:
    def test_start_uses_the_supplied_candidate(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-backend-a", _candidate_a())
        context = _context(stack, "sess-backend-a")
        assert context["analysis"]["candidate_id"] == "candidate-a"
        assert context["plan"]["candidate_id"] == "candidate-a"
        assert context["analysis"]["profile"]["name"] == "Ada Systems"

    def test_api_request_delivers_candidate_verbatim(self, stack: SimpleNamespace, client) -> None:
        payload = _candidate_a().model_dump(mode="json")
        resp = client.post(
            "/api/interview",
            json={"sessionId": "api-candidate", "candidate": payload},
        )
        assert resp.status_code == 200
        context = stack.session_manager.get_session("api-candidate").context
        assert context["analysis"]["candidate_id"] == payload["id"]
        assert context["analysis"]["profile"]["role"] == payload["role"]
        assert context["analysis"]["profile"]["focus_areas"] == payload["focus_areas"]


# --- 2. Candidate analysis differs where profiles differ --------------------


class TestAnalysisIsCandidateSpecific:
    def test_analysis_differs_where_profiles_differ(self, stack: SimpleNamespace) -> None:
        analysis_a = stack.candidate_analyzer.analyze_profile(_candidate_a())
        analysis_b = stack.candidate_analyzer.analyze_profile(_candidate_b())
        assert analysis_a.candidate_id != analysis_b.candidate_id
        assert analysis_a.areas_for_further_assessment != analysis_b.areas_for_further_assessment
        assert analysis_a.strengths != analysis_b.strengths
        assert analysis_a.learning_signals != analysis_b.learning_signals


# --- 3. Planner receives the candidate analysis ------------------------------


class TestPlannerReceivesAnalysis:
    def test_plan_carries_the_analysis_it_was_built_from(self, stack: SimpleNamespace) -> None:
        analysis = stack.candidate_analyzer.analyze_profile(_candidate_a())
        plan = stack.planner.plan_for(analysis, stack.curriculum)
        assert plan.candidate_id == analysis.candidate_id == "candidate-a"


# --- 4/8. Plans differ based on candidate profile ---------------------------


class TestPlanDifferencesByProfile:
    def test_plans_differ_between_different_profiles(self, stack: SimpleNamespace) -> None:
        analysis_a = stack.candidate_analyzer.analyze_profile(_candidate_a())
        analysis_b = stack.candidate_analyzer.analyze_profile(_candidate_b())
        plan_a = stack.planner.plan_for(analysis_a, stack.curriculum)
        plan_b = stack.planner.plan_for(analysis_b, stack.curriculum)

        assert plan_a.questions[0].topic_id == "topic-systems"
        assert plan_b.questions[0].topic_id == "topic-databases"
        assert plan_a.questions[0].curriculum_question_id != plan_b.questions[0].curriculum_question_id
        assert [q.curriculum_question_id for q in plan_a.questions] != [
            q.curriculum_question_id for q in plan_b.questions
        ]

    def test_engine_plans_differ_between_candidates(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-eng-a", _candidate_a())
        stack.engine.start("sess-eng-b", _candidate_b())
        assert _questions(stack, "sess-eng-a")[0]["text"] != _questions(stack, "sess-eng-b")[0]["text"]


# --- 5. First question comes from the generated plan -------------------------


class TestFirstQuestionFromPlan:
    def test_reply_and_current_use_plan_question_one(self, stack: SimpleNamespace) -> None:
        resp = stack.engine.start("sess-first", _candidate_a())
        context = _context(stack, "sess-first")
        first = context["plan"]["questions"][0]
        assert context["current"]["curriculum_question_id"] == first["curriculum_question_id"]
        assert context["current"]["text"] == first["text"]
        assert first["text"] in resp.reply


# --- 6. Deterministic plan across repeated starts ----------------------------


class TestDeterministicAcrossStarts:
    def test_same_candidate_same_plan_on_repeated_starts(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-det-1", _candidate_a())
        stack.engine.start("sess-det-2", _candidate_a())
        assert _questions(stack, "sess-det-1") == _questions(stack, "sess-det-2")


# --- 7. Session isolation remains intact -------------------------------------


class TestSessionIsolation:
    def test_each_session_keeps_its_own_candidate_plan_and_state(
        self, stack: SimpleNamespace
    ) -> None:
        stack.engine.start("sess-iso-a", _candidate_a())
        stack.engine.start("sess-iso-b", _candidate_b())
        ctx_a = _context(stack, "sess-iso-a")
        ctx_b = _context(stack, "sess-iso-b")
        assert ctx_a["analysis"]["candidate_id"] == "candidate-a"
        assert ctx_b["analysis"]["candidate_id"] == "candidate-b"
        assert [q["curriculum_question_id"] for q in ctx_a["plan"]["questions"]] != [
            q["curriculum_question_id"] for q in ctx_b["plan"]["questions"]
        ]

        stack.engine.handle_answer("sess-iso-a", _full_answer(ctx_a["current"]))
        ctx_b_after = _context(stack, "sess-iso-b")
        assert ctx_b_after["primary_index"] == 0
        assert ctx_b_after["primary_answered"] == 0
        assert ctx_b_after["analysis"]["candidate_id"] == "candidate-b"


# --- Debug report (requirement 7) -------------------------------------------


class TestPersonalizationDebugLogging:
    def test_reports_selected_topics_and_questions_for_two_candidates(
        self, stack: SimpleNamespace
    ) -> None:
        analysis_a = stack.candidate_analyzer.analyze_profile(_candidate_a())
        analysis_b = stack.candidate_analyzer.analyze_profile(_candidate_b())
        plan_a = stack.planner.plan_for(analysis_a, stack.curriculum)
        plan_b = stack.planner.plan_for(analysis_b, stack.curriculum)

        print(f"\ncandidate A ({analysis_a.candidate_id}) -> selected topics/questions:")
        for question in plan_a.questions:
            print(f"  {question.sequence}. [{question.topic_id}] {question.text}")

        print(f"candidate B ({analysis_b.candidate_id}) -> selected topics/questions:")
        for question in plan_b.questions:
            print(f"  {question.sequence}. [{question.topic_id}] {question.text}")

        assert plan_a.questions[0].topic_id != plan_b.questions[0].topic_id
        assert plan_a.questions[0].curriculum_question_id != plan_b.questions[0].curriculum_question_id
