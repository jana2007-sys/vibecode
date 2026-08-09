"""Tests for the private enrollment archive (EnrollmentStore).

When an enrolled (custom-*) candidate completes an interview, their profile and
full report are archived into a separate private SQLite database. Predefined
seeded candidates (``candidate-*``) are never archived because they never
enrolled through the app.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database.connection import Database
from app.database.repositories.candidate_repository import CandidateRepository
from app.database.repositories.enrollment_repository import EnrollmentRepository
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.memory.conversation_memory import ConversationMemory
from app.models.candidate import CandidateProfile, SkillLevel
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.enrollment_store import EnrollmentStore
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator
from app.services.gemini_service import GeminiService
from app.services.interview_engine import InterviewEngine
from app.services.memory_engine import MemoryEngine
from app.services.question_planner import QuestionPlanner
from app.services.report_service import ReportService
from app.services.session_manager import SessionManager
from app.utils.config import Settings

SYNTHETIC_CURRICULUM = {
    "id": "curriculum-001",
    "title": "Synthetic Interview Curriculum",
    "description": "Five topics with varied-difficulty questions for archive tests.",
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


def _enrolled_candidate() -> CandidateProfile:
    """A candidate who enrolled through the app (custom-* id)."""
    return CandidateProfile(
        id="custom-archive-001",
        name="Riley Chen",
        role="Data Engineer",
        years_of_experience=3.0,
        experience_level="mid",
        skills=[SkillLevel(name="Python", level="advanced")],
        learning_journey=[],
        preferred_languages=["Python", "SQL"],
        focus_areas=["Databases"],
        notes="Enrolled through the profile form.",
    )


def _seeded_candidate() -> CandidateProfile:
    """A predefined (non-enrolled) candidate."""
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


def _build_stack(tmp_path: Path) -> SimpleNamespace:
    """Wire the engine plus a private archive against temp databases."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "curriculum.json").write_text(json.dumps(SYNTHETIC_CURRICULUM), encoding="utf-8")

    db = Database(tmp_path / "interview.db")
    db.initialize()
    private_db = Database(tmp_path / "private.db", schema="private_schema.sql")
    private_db.initialize()

    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    score_repo = ScoreRepository(db)
    feedback_repo = FeedbackRepository(db)
    candidate_repo = CandidateRepository(db)
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
    report_service = ReportService(
        candidate_repository=candidate_repo,
        session_repository=session_repo,
        message_repository=message_repo,
        feedback_repository=feedback_repo,
        score_repository=score_repo,
    )
    enrollment_repo = EnrollmentRepository(private_db)
    enrollment_store = EnrollmentStore(
        repository=enrollment_repo,
        report_service=report_service,
        candidate_repository=candidate_repo,
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
        candidate_repository=candidate_repo,
        enrollment_store=enrollment_store,
    )
    return SimpleNamespace(
        engine=engine,
        store=enrollment_store,
        enrollment_repo=enrollment_repo,
        candidate_repo=candidate_repo,
        session_manager=session_manager,
    )


@pytest.fixture()
def stack(tmp_path: Path) -> SimpleNamespace:
    """The wired engine + private archive stack."""
    return _build_stack(tmp_path)


def _full_answer(question: dict) -> str:
    return "I can explain this. " + ", ".join(question["expects"]) + " are all important concepts."


def _enroll_candidate_row(stack: SimpleNamespace, candidate: CandidateProfile) -> None:
    """Persist an enrolled candidate row with an email, as POST /api/candidates does."""
    from app.models.common import utc_now

    stack.candidate_repo.upsert(
        candidate_id=candidate.id,
        name=candidate.name,
        email="riley.chen@example.com",
        role=candidate.role,
        years_of_experience=candidate.years_of_experience,
        experience_level=candidate.experience_level,
        skills=[skill.model_dump(mode="json") for skill in candidate.skills],
        learning_journey=[],
        preferred_languages=candidate.preferred_languages,
        focus_areas=candidate.focus_areas,
        strengths=["Collaboration", "Debugging"],
        notes=candidate.notes,
        now=utc_now(),
    )


def _drive_to_done(stack: SimpleNamespace, candidate: CandidateProfile, session_id: str):
    """Run a full interview to completion using only full answers."""
    if candidate.id.startswith("custom-"):
        _enroll_candidate_row(stack, candidate)
    resp = stack.engine.start(session_id, candidate)
    while not resp.done:
        current = stack.session_manager.get_session(session_id).context["current"]
        resp = stack.engine.handle_answer(session_id, _full_answer(current))
    return resp


class TestArchiveOnCompletion:
    def test_custom_candidate_completion_archives_profile_and_report(self, stack) -> None:
        _drive_to_done(stack, _enrolled_candidate(), "sess-custom-1")

        enrolled = stack.enrollment_repo.get_candidate("custom-archive-001")
        assert enrolled is not None
        assert enrolled["name"] == "Riley Chen"
        assert enrolled["email"] == "riley.chen@example.com"
        assert enrolled["skills"][0]["name"] == "Python"

        reports = stack.enrollment_repo.list_reports("custom-archive-001")
        assert len(reports) == 1
        report = reports[0]["report"]
        assert report["session_id"] == "sess-custom-1"
        assert report["candidate"]["name"] == "Riley Chen"
        assert report["feedback"]["overall_score"] >= 0
        assert len(report["messages"]) > 0

    def test_seeded_candidate_is_never_archived(self, stack) -> None:
        _drive_to_done(stack, _seeded_candidate(), "sess-seeded-1")

        assert stack.enrollment_repo.get_candidate("candidate-001") is None
        assert stack.enrollment_repo.list_reports() == []

    def test_second_interview_adds_another_report_and_keeps_one_candidate(self, stack) -> None:
        candidate = _enrolled_candidate()
        _drive_to_done(stack, candidate, "sess-custom-1")
        _drive_to_done(stack, candidate, "sess-custom-2")

        assert stack.enrollment_repo.get_candidate("custom-archive-001") is not None
        reports = stack.enrollment_repo.list_reports("custom-archive-001")
        assert {report["session_id"] for report in reports} == {"sess-custom-1", "sess-custom-2"}

    def test_list_enrollments_returns_candidate_with_reports(self, stack) -> None:
        _drive_to_done(stack, _enrolled_candidate(), "sess-custom-1")

        enrollments = stack.enrollment_repo.list_enrollments()
        assert len(enrollments) == 1
        assert enrollments[0]["id"] == "custom-archive-001"
        assert len(enrollments[0]["reports"]) == 1


class TestStoreDirect:
    def test_unknown_candidate_is_not_archived(self, stack) -> None:
        assert stack.store.archive_completed_interview("custom-nope", "sess-x") is False
        assert stack.enrollment_repo.list_enrollments() == []

    def test_seeded_candidate_is_not_archived(self, stack) -> None:
        _drive_to_done(stack, _seeded_candidate(), "sess-seeded-1")
        assert stack.store.archive_completed_interview("candidate-001", "sess-seeded-1") is False
