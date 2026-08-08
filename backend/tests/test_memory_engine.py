"""Focused tests for the hardened MemoryEngine (Step 5B).

Every test drives the real InterviewEngine against a real temporary SQLite
database (no mocks), then verifies the durable, session-scoped memory layer:
what is persisted, how it is retrieved, session isolation, read-only completed
sessions, chronological ordering, follow-up vs primary distinction, survival
across fresh service instances, and foreign-key integrity.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
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
from app.models.session import SessionCreate
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
from app.utils.errors import NotFoundError, ValidationError

#: Synthetic 5-topic curriculum (id ``curriculum-001``) matching the engine's
#: default curriculum id, so the full conversational flow is deterministic.
SYNTHETIC_CURRICULUM = {
    "id": "curriculum-001",
    "title": "Synthetic Interview Curriculum",
    "description": "Five topics with varied-difficulty questions for memory tests.",
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
    if isinstance(payload, Path):
        shutil.copy(payload, data_dir / "curriculum.json")
    else:
        (data_dir / "curriculum.json").write_text(json.dumps(payload), encoding="utf-8")
    return data_dir


def _candidate() -> CandidateProfile:
    """A straightforward candidate profile used across the tests."""
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
    """Wire every engine collaborator against a temp curriculum + temp DB."""
    data_dir = _write_curriculum(tmp_path, SYNTHETIC_CURRICULUM)
    db_path = tmp_path / "interview.db"
    db = Database(db_path)
    db.initialize()

    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    score_repo = ScoreRepository(db)
    feedback_repo = FeedbackRepository(db)
    session_manager = SessionManager(session_repo)
    gemini = GeminiService(settings=Settings(gemini_enabled=False))
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
        memory=memory_engine,
        session_manager=session_manager,
        message_repo=message_repo,
        score_repo=score_repo,
        feedback_repo=feedback_repo,
        db_path=db_path,
    )


@pytest.fixture()
def stack(tmp_path: Path) -> SimpleNamespace:
    """The standard wired interview + memory stack."""
    return _build_stack(tmp_path)


# --- Small helpers -----------------------------------------------------------


def _questions(stack: SimpleNamespace, session_id: str) -> list[dict]:
    return stack.session_manager.get_session(session_id).context["plan"]["questions"]


def _full_answer(question: dict) -> str:
    """An answer that covers every expected concept of ``question``."""
    return "I can explain this. " + ", ".join(question["expects"]) + " are all important concepts."


def _weak_answer(_question: dict) -> str:
    return "I'm not sure about this one."


def _drive_to_done(stack: SimpleNamespace, responder, session_id: str = "sess-001") -> object:
    """Run a full interview, answering every turn with ``responder``."""
    resp = stack.engine.start(session_id, _candidate())
    while not resp.done:
        resp = stack.engine.handle_answer(session_id, responder(_current(stack, session_id)))
    return resp


def _current(stack: SimpleNamespace, session_id: str) -> dict:
    return stack.session_manager.get_session(session_id).context["current"]


# --- Empty / fresh session ---------------------------------------------------


class TestFreshSession:
    def test_new_session_has_empty_interview_memory(self, stack: SimpleNamespace) -> None:
        stack.session_manager.create_session(
            SessionCreate(candidate_id="candidate-001", curriculum_id="curriculum-001"),
            session_id="sess-empty",
        )
        memory = stack.memory.get_session_memory("sess-empty")
        assert memory["state"] == "START"
        assert memory["answers"] == []
        assert memory["evaluations"] == []
        assert memory["asked_questions"] == []
        assert memory["topics_covered"] == []
        assert memory["current_question"] is None
        assert memory["plan"] == {}
        assert memory["feedback"] is None
        assert stack.memory.get_conversation_history("sess-empty") == []
        assert stack.memory.get_previous_answers("sess-empty") == []
        assert stack.memory.get_evaluations("sess-empty") == []
        assert stack.memory.get_missing_concepts("sess-empty") == []
        assert stack.memory.get_covered_topics("sess-empty") == []

    def test_nonexistent_session_raises_not_found(self, stack: SimpleNamespace) -> None:
        with pytest.raises(NotFoundError):
            stack.memory.get_session_memory("sess-ghost")
        with pytest.raises(NotFoundError):
            stack.memory.get_conversation_history("sess-ghost")
        with pytest.raises(NotFoundError):
            stack.memory.get_previous_answers("sess-ghost")
        with pytest.raises(NotFoundError):
            stack.memory.get_evaluations("sess-ghost")
        with pytest.raises(NotFoundError):
            stack.memory.get_current_question("sess-ghost")
        with pytest.raises(NotFoundError):
            stack.memory.get_interview_summary_context("sess-ghost")


# --- Persisted content -------------------------------------------------------


class TestPersistedContent:
    def test_candidate_context_is_persisted(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-cand", _candidate())
        memory = stack.memory.get_session_memory("sess-cand")
        assert memory["candidate_id"] == "candidate-001"
        assert memory["curriculum_id"] == "curriculum-001"
        assert memory["analysis"]["candidate_id"] == "candidate-001"
        assert memory["analysis"]["profile"]["name"] == "Alex Rivera"
        assert memory["analysis"]["profile"]["role"] == "Backend Engineer"

    def test_interview_plan_is_persisted(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-plan", _candidate())
        memory = stack.memory.get_session_memory("sess-plan")
        plan = memory["plan"]
        assert plan["total_questions"] == 8
        assert len(plan["questions"]) == 8
        assert plan["curriculum_id"] == "curriculum-001"
        assert memory["primary_question_count"] == 0
        assert memory["follow_up_count"] == 0
        assert memory["current_question"] is not None

    def test_question_answer_history_is_retrievable(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-hist", _candidate())
        questions = _questions(stack, "sess-hist")
        stack.engine.handle_answer("sess-hist", _full_answer(questions[0]))
        stack.engine.handle_answer("sess-hist", _full_answer(questions[1]))

        answers = stack.memory.get_previous_answers("sess-hist")
        assert len(answers) == 2
        assert [a["question_id"] for a in answers] == [
            questions[0]["curriculum_question_id"],
            questions[1]["curriculum_question_id"],
        ]

        asked = stack.memory.get_asked_questions("sess-hist")
        assert len(asked) == 3
        assert [q["curriculum_question_id"] for q in asked] == [
            questions[i]["curriculum_question_id"] for i in range(3)
        ]

        current = stack.memory.get_current_question("sess-hist")
        assert current["curriculum_question_id"] == questions[2]["curriculum_question_id"]

        history = stack.memory.get_conversation_history("sess-hist")
        roles = [m["role"] for m in history]
        assert roles == ["interviewer", "candidate", "interviewer", "candidate", "interviewer"]

    def test_evaluation_history_is_retrievable(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-eval", _candidate())
        questions = _questions(stack, "sess-eval")
        stack.engine.handle_answer("sess-eval", _full_answer(questions[0]))
        stack.engine.handle_answer("sess-eval", _weak_answer(questions[1]))

        evaluations = stack.memory.get_evaluations("sess-eval")
        assert len(evaluations) == 2
        assert evaluations[0]["score"] == 10.0
        assert evaluations[1]["score"] == 0.0
        assert [e["question_id"] for e in evaluations] == [
            questions[0]["curriculum_question_id"],
            questions[1]["curriculum_question_id"],
        ]
        persisted = stack.score_repo.list_by_session("sess-eval")
        assert len(persisted) == 2

    def test_missing_concepts_are_retrievable(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-miss", _candidate())
        questions = _questions(stack, "sess-miss")
        stack.engine.handle_answer("sess-miss", _weak_answer(questions[0]))
        missing = stack.memory.get_missing_concepts("sess-miss")
        assert set(missing) == set(questions[0]["expects"])

    def test_covered_topics_are_retrievable(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-top", _candidate())
        questions = _questions(stack, "sess-top")
        covered = stack.memory.get_covered_topics("sess-top")
        assert covered == [questions[0]["topic_id"]]
        stack.engine.handle_answer("sess-top", _full_answer(questions[0]))
        stack.engine.handle_answer("sess-top", _full_answer(questions[1]))
        covered = stack.memory.get_covered_topics("sess-top")
        assert questions[0]["topic_id"] in covered
        assert questions[1]["topic_id"] in covered
        assert len(set(covered)) == len(covered)

    def test_interview_summary_context(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-sum", _candidate())
        questions = _questions(stack, "sess-sum")
        stack.engine.handle_answer("sess-sum", _weak_answer(questions[0]))
        summary = stack.memory.get_interview_summary_context("sess-sum")
        assert summary["candidate_name"] == "Alex Rivera"
        assert summary["state"] == "FOLLOW_UP"
        assert summary["current_question"]["question_id"] == questions[0]["curriculum_question_id"]
        assert summary["current_question"]["difficulty"] == questions[0]["difficulty"]
        assert summary["missing_concepts"]
        assert summary["total_questions"] == 8


# --- Isolation ---------------------------------------------------------------


class TestSessionIsolation:
    def test_session_a_cannot_access_session_b(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-a", _candidate())
        stack.engine.start("sess-b", _candidate())
        question_a = _questions(stack, "sess-a")[0]
        question_b = _questions(stack, "sess-b")[0]
        assert question_a["curriculum_question_id"] == question_b["curriculum_question_id"]

        stack.engine.handle_answer("sess-a", "ANSWER FOR A covers " + ", ".join(question_a["expects"]))
        stack.engine.handle_answer("sess-b", "ANSWER FOR B covers " + ", ".join(question_b["expects"]))

        answers_a = stack.memory.get_previous_answers("sess-a")
        answers_b = stack.memory.get_previous_answers("sess-b")
        assert len(answers_a) == 1
        assert len(answers_b) == 1
        assert "ANSWER FOR A" in answers_a[0]["answer"]
        assert "ANSWER FOR B" in answers_b[0]["answer"]
        assert "ANSWER FOR B" not in answers_a[0]["answer"]
        assert "ANSWER FOR A" not in answers_b[0]["answer"]

        history_a = stack.memory.get_conversation_history("sess-a")
        assert all(message["session_id"] == "sess-a" for message in history_a)
        assert all(message["session_id"] == "sess-b" for message in stack.memory.get_conversation_history("sess-b"))

        assert stack.score_repo.list_by_session("sess-a")[0]["question_id"] == question_a["curriculum_question_id"]
        assert stack.score_repo.list_by_session("sess-b")[0]["question_id"] == question_b["curriculum_question_id"]


# --- Completed sessions ------------------------------------------------------


class TestCompletedSession:
    def test_completed_session_remains_readable(self, stack: SimpleNamespace) -> None:
        _drive_to_done(stack, _full_answer)
        memory = stack.memory.get_session_memory("sess-001")
        assert memory["state"] == "COMPLETED"
        assert memory["completed_at"] is not None
        assert len(memory["answers"]) == 8
        assert len(stack.memory.get_conversation_history("sess-001")) > 0
        assert stack.memory.get_current_question("sess-001") is None
        assert memory["feedback"] is not None
        assert memory["feedback"]["overall_score"] == 10.0
        summary = stack.memory.get_interview_summary_context("sess-001")
        assert summary["state"] == "COMPLETED"
        assert summary["feedback"] is not None

    def test_completed_session_cannot_be_mutated(self, stack: SimpleNamespace) -> None:
        _drive_to_done(stack, _full_answer)
        with pytest.raises(ValidationError, match="already completed"):
            stack.engine.handle_answer("sess-001", "one more answer")
        memory = stack.memory.get_session_memory("sess-001")
        assert memory["state"] == "COMPLETED"
        assert len(memory["answers"]) == 8
        assert len(memory["evaluations"]) == 8
        assert stack.feedback_repo.get_by_session("sess-001") is not None


# --- Ordering / follow-ups ---------------------------------------------------


class TestOrderingAndFollowUps:
    def test_multiple_answers_preserve_chronological_order(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-ord", _candidate())
        questions = _questions(stack, "sess-ord")
        for index in range(4):
            stack.engine.handle_answer("sess-ord", _full_answer(questions[index]))

        answers = stack.memory.get_previous_answers("sess-ord")
        assert len(answers) == 4
        assert [a["question_id"] for a in answers] == [
            questions[index]["curriculum_question_id"] for index in range(4)
        ]

        history = stack.memory.get_conversation_history("sess-ord")
        expected_roles = ["interviewer", "candidate"] * 4 + ["interviewer"]
        assert [message["role"] for message in history] == expected_roles

    def test_follow_ups_remain_distinguishable_from_primaries(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-fu", _candidate())
        questions = _questions(stack, "sess-fu")
        resp = stack.engine.handle_answer("sess-fu", _weak_answer(questions[0]))
        assert resp.done is False
        stack.engine.handle_answer("sess-fu", _full_answer(questions[0]))

        kinds = [evaluation["kind"] for evaluation in stack.memory.get_evaluations("sess-fu")]
        assert kinds == ["primary", "follow_up"]

        memory = stack.memory.get_session_memory("sess-fu")
        assert memory["primary_question_count"] == 1
        assert memory["follow_up_count"] == 1
        assert memory["pending_follow_up"] is None

        message_kinds = [message["metadata"].get("kind") for message in stack.memory.get_conversation_history("sess-fu")]
        assert message_kinds.count("question") == 2
        assert message_kinds.count("answer") == 2
        assert message_kinds.count("follow_up") == 1


# --- Durability --------------------------------------------------------------


class TestDurability:
    def test_memory_survives_fresh_service_instance(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-fresh", _candidate())
        questions = _questions(stack, "sess-fresh")
        stack.engine.handle_answer("sess-fresh", _full_answer(questions[0]))
        stack.engine.handle_answer("sess-fresh", _weak_answer(questions[1]))

        db2 = Database(stack.db_path)
        db2.initialize()
        memory2 = MemoryEngine(
            conversation_memory=ConversationMemory(),
            gemini_service=GeminiService(settings=Settings(gemini_enabled=False)),
            session_repository=SessionRepository(db2),
            message_repository=MessageRepository(db2),
            score_repository=ScoreRepository(db2),
            feedback_repository=FeedbackRepository(db2),
        )

        memory = memory2.get_session_memory("sess-fresh")
        assert memory["candidate_id"] == "candidate-001"
        assert memory["analysis"]["candidate_id"] == "candidate-001"
        assert memory["plan"]["total_questions"] == 8
        assert len(memory["answers"]) == 2
        assert len(memory["evaluations"]) == 2
        assert len(memory2.get_conversation_history("sess-fresh")) >= 4
        assert stack.memory.get_recent("sess-fresh")  # live window still works
        assert memory2.get_recent("sess-fresh") == []  # fresh instance starts with empty live window

    def test_existing_database_foreign_keys_remain_valid(self, stack: SimpleNamespace) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            stack.score_repo.create(
                score_id="score-ghost",
                session_id="sess-ghost",
                topic_id="t",
                question_id="q",
                score=1.0,
                rationale="",
                created_at=datetime.now(timezone.utc),
            )
        with pytest.raises(sqlite3.IntegrityError):
            stack.message_repo.create(
                message_id="msg-ghost",
                session_id="sess-ghost",
                role="interviewer",
                content="hello",
                metadata={},
                created_at=datetime.now(timezone.utc),
            )
