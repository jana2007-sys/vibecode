"""Focused tests for the Phase 2 Step 4 InterviewEngine + interactive contract.

Uses a synthetic 5-topic curriculum (id ``curriculum-001``) with 14 grounded
questions across easy/medium/hard, matching the engine's default curriculum id,
so the full conversational flow is deterministic. The shipped 3-topic
curriculum is used to verify the clear-failure path.

Engine-level tests cover every required behavior; API-level tests exercise the
POST /api/interview wire contract and are skipped when httpx is unavailable.
"""

from __future__ import annotations

import json
import shutil
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
from app.models.session import InterviewState, SessionCreate
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator
from app.services.gemini_service import GeminiService
from app.services.interview_engine import DEFAULT_CURRICULUM_ID, InterviewEngine
from app.services.memory_engine import MemoryEngine
from app.services.question_planner import MIN_TOPICS, QuestionPlanner
from app.services.session_manager import SessionManager
from app.utils.config import Settings
from app.utils.errors import NotFoundError, StateTransitionError, ValidationError

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"

#: Synthetic 5-topic curriculum with 14 grounded questions across all tiers.
SYNTHETIC_CURRICULUM = {
    "id": "curriculum-001",
    "title": "Synthetic Interview Curriculum",
    "description": "Five topics with varied-difficulty questions for engine tests.",
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


def _build_stack(tmp_path: Path, curriculum_payload: object = SYNTHETIC_CURRICULUM) -> SimpleNamespace:
    """Wire every engine collaborator against a temp curriculum + temp DB."""
    data_dir = _write_curriculum(tmp_path, curriculum_payload)
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
        message_repo=message_repo,
        score_repo=score_repo,
        feedback_repo=feedback_repo,
        curriculum=Curriculum(**SYNTHETIC_CURRICULUM),
    )


@pytest.fixture()
def stack(tmp_path: Path) -> SimpleNamespace:
    """The standard wired interview stack."""
    return _build_stack(tmp_path)


# --- Helpers ----------------------------------------------------------------


def _questions(stack: SimpleNamespace, session_id: str) -> list[dict]:
    """The planned questions for a session, in ask order."""
    return stack.session_manager.get_session(session_id).context["plan"]["questions"]


def _context(stack: SimpleNamespace, session_id: str) -> dict:
    return stack.session_manager.get_session(session_id).context


def _current(stack: SimpleNamespace, session_id: str) -> dict:
    return _context(stack, session_id)["current"]


def _full_answer(question: dict) -> str:
    """An answer that covers every expected concept of ``question``."""
    return "I can explain this. " + ", ".join(question["expects"]) + " are all important concepts."


def _weak_answer(_question: dict) -> str:
    return "I'm not sure about this one."


def _drive_to_done(stack: SimpleNamespace, responder, session_id: str = "sess-001"):
    """Run a full interview, answering every turn with ``responder``."""
    resp = stack.engine.start(session_id, _candidate())
    while not resp.done:
        resp = stack.engine.handle_answer(session_id, responder(_current(stack, session_id)))
    return resp


# --- Start ------------------------------------------------------------------


class TestStart:
    def test_start_returns_first_question_and_question_state(self, stack: SimpleNamespace) -> None:
        resp = stack.engine.start("sess-start", _candidate())
        assert resp.done is False
        assert resp.feedback is None
        questions = _questions(stack, "sess-start")
        assert questions[0]["text"] in resp.reply
        session = stack.session_manager.get_session("sess-start")
        assert InterviewState(session.state) == InterviewState.QUESTION
        context = session.context
        assert context["current"]["text"] == questions[0]["text"]
        assert context["primary_question_count"] == 0
        assert context["phase"] == "question"

    def test_start_persists_plan_and_analysis(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-plan", _candidate())
        context = _context(stack, "sess-plan")
        assert context["plan"]["total_questions"] == 8
        assert len(context["plan"]["questions"]) == 8
        assert context["analysis"]["candidate_id"] == "candidate-001"
        assert context["curriculum_id"] == DEFAULT_CURRICULUM_ID

    def test_start_twice_raises_validation_error(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-restart", _candidate())
        with pytest.raises(ValidationError, match="already started"):
            stack.engine.start("sess-restart", _candidate())

    def test_start_real_curriculum_fails_validation(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, REAL_DATA_DIR / "curriculum.json")
        with pytest.raises(ValidationError, match="at least 4 usable topics"):
            stack.engine.start("sess-real", _candidate())


# --- Answer flow ------------------------------------------------------------


class TestAnswerFlow:
    def test_strong_answer_advances_to_next_question(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-next", _candidate())
        questions = _questions(stack, "sess-next")
        resp = stack.engine.handle_answer("sess-next", _full_answer(questions[0]))
        assert resp.done is False
        assert resp.reply == questions[1]["text"]
        assert InterviewState(stack.session_manager.get_session("sess-next").state) == InterviewState.QUESTION
        assert _context(stack, "sess-next")["primary_question_count"] == 1
        assert _context(stack, "sess-next")["primary_index"] == 1

    def test_weak_answer_triggers_one_follow_up(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-fu", _candidate())
        questions = _questions(stack, "sess-fu")
        resp = stack.engine.handle_answer("sess-fu", _weak_answer(questions[0]))
        assert resp.done is False
        assert InterviewState(stack.session_manager.get_session("sess-fu").state) == InterviewState.FOLLOW_UP
        context = _context(stack, "sess-fu")
        assert context["phase"] == "follow_up"
        assert context["pending_follow_up"] == questions[0]["expects"][0]
        assert context["follow_up_count"] == 0
        assert questions[0]["expects"][0] in resp.reply

    def test_follow_up_does_not_replace_primary(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-fu2", _candidate())
        questions = _questions(stack, "sess-fu2")
        stack.engine.handle_answer("sess-fu2", _weak_answer(questions[0]))
        resp = stack.engine.handle_answer("sess-fu2", _full_answer(questions[0]))
        assert resp.reply == questions[1]["text"]
        context = _context(stack, "sess-fu2")
        assert context["primary_question_count"] == 1
        assert context["follow_up_count"] == 1
        assert context["pending_follow_up"] is None
        assert context["phase"] == "question"

    def test_answers_and_scores_are_persisted(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-persist", _candidate())
        questions = _questions(stack, "sess-persist")
        stack.engine.handle_answer("sess-persist", _full_answer(questions[0]))

        messages = stack.message_repo.list_by_session("sess-persist")
        assert [message["role"] for message in messages] == ["interviewer", "candidate", "interviewer"]
        assert messages[1]["metadata"]["question_id"] == questions[0]["curriculum_question_id"]
        assert messages[2]["content"] == questions[1]["text"]

        scores = stack.score_repo.list_by_session("sess-persist")
        assert len(scores) == 1
        assert scores[0]["question_id"] == questions[0]["curriculum_question_id"]
        assert scores[0]["score"] == 10.0

    def test_weak_answer_scores_zero(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-zero", _candidate())
        questions = _questions(stack, "sess-zero")
        stack.engine.handle_answer("sess-zero", _weak_answer(questions[0]))
        scores = stack.score_repo.list_by_session("sess-zero")
        assert scores[0]["score"] == 0.0

    def test_eight_primaries_then_done(self, stack: SimpleNamespace) -> None:
        resp = _drive_to_done(stack, _full_answer)
        assert resp.done is True
        context = _context(stack, "sess-001")
        assert context["primary_question_count"] == 8
        assert context["primary_answered"] == 8
        assert context["follow_up_count"] == 0
        assert InterviewState(stack.session_manager.get_session("sess-001").state) == InterviewState.COMPLETED

    def test_at_least_four_topics_covered(self, stack: SimpleNamespace) -> None:
        resp = _drive_to_done(stack, _full_answer)
        assert resp.done is True
        covered = set(_context(stack, "sess-001")["topics_covered"])
        assert len(covered) >= MIN_TOPICS

    def test_weak_interview_completes_with_follow_ups(self, stack: SimpleNamespace) -> None:
        resp = _drive_to_done(stack, _weak_answer)
        assert resp.done is True
        context = _context(stack, "sess-001")
        assert context["primary_question_count"] == 8
        assert context["follow_up_count"] >= 1
        assert resp.feedback is not None
        assert len(resp.feedback.gaps) > 0

    def test_completed_session_rejects_further_answers(self, stack: SimpleNamespace) -> None:
        _drive_to_done(stack, _full_answer)
        with pytest.raises(ValidationError, match="already completed"):
            stack.engine.handle_answer("sess-001", "one more?")

    def test_answer_unknown_session_raises_not_found(self, stack: SimpleNamespace) -> None:
        with pytest.raises(NotFoundError):
            stack.engine.handle_answer("sess-missing", "hello?")


# --- Feedback ---------------------------------------------------------------


class TestFeedback:
    def test_done_response_carries_feedback_fields(self, stack: SimpleNamespace) -> None:
        resp = _drive_to_done(stack, _full_answer)
        assert resp.feedback is not None
        assert resp.feedback.summary
        assert isinstance(resp.feedback.strengths, list)
        assert isinstance(resp.feedback.gaps, list)
        assert isinstance(resp.feedback.next, list)

    def test_feedback_report_is_persisted(self, stack: SimpleNamespace) -> None:
        _drive_to_done(stack, _full_answer)
        row = stack.feedback_repo.get_by_session("sess-001")
        assert row is not None
        assert row["overall_score"] == 10.0
        assert row["summary"]
        assert row["strengths"]


# --- Evaluation engine ------------------------------------------------------


class TestEvaluationEngine:
    def test_evaluate_topic_averages_scores(self, stack: SimpleNamespace) -> None:
        stack.session_manager.create_session(
            SessionCreate(candidate_id="candidate-001", curriculum_id=DEFAULT_CURRICULUM_ID),
            session_id="sess-eval",
        )
        evaluator = stack.engine._evaluator
        evaluator.evaluate_answer("sess-eval", "topic-x", "q1", "covers immutable and mutable", expects=["immutable", "mutable"])
        evaluator.evaluate_answer("sess-eval", "topic-x", "q2", "nothing relevant", expects=["immutable", "mutable"])
        assert evaluator.evaluate_topic("sess-eval", "topic-x") == 5.0
        assert evaluator.evaluate_topic("sess-eval", "topic-other") == 0.0

    def test_state_machine_rejects_illegal_transition(self, stack: SimpleNamespace) -> None:
        stack.engine.start("sess-machine", _candidate())
        with pytest.raises(StateTransitionError):
            stack.session_manager.advance("sess-machine", InterviewState.COMPLETED)


# --- API contract (skipped when httpx is unavailable) -----------------------


def _api_client(stack: SimpleNamespace):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_interview_engine
    from app.api.middleware import setup_error_handlers
    from app.api.routes.interview import router

    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_interview_engine] = lambda: stack.engine
    return TestClient(app)


class TestApiContract:
    @pytest.fixture()
    def client(self, stack: SimpleNamespace):
        pytest.importorskip("httpx")
        return _api_client(stack)

    def test_start_and_answer_round_trip(self, client) -> None:
        start = client.post(
            "/api/interview",
            json={"sessionId": "api-1", "candidate": _candidate().model_dump(mode="json")},
        )
        assert start.status_code == 200
        body = start.json()
        assert body["done"] is False
        assert body["reply"]

        answer = client.post("/api/interview", json={"sessionId": "api-1", "message": "I can explain the difference."})
        assert answer.status_code == 200
        assert answer.json()["done"] is False
        assert answer.json()["reply"]

    def test_missing_session_id_is_422(self, client) -> None:
        resp = client.post("/api/interview", json={"candidate": _candidate().model_dump(mode="json")})
        assert resp.status_code == 422

    def test_candidate_and_message_conflict_is_422(self, client) -> None:
        resp = client.post(
            "/api/interview",
            json={
                "sessionId": "api-bad",
                "candidate": _candidate().model_dump(mode="json"),
                "message": "both should fail",
            },
        )
        assert resp.status_code == 422

    def test_continue_unknown_session_is_404(self, client) -> None:
        resp = client.post("/api/interview", json={"sessionId": "api-nope", "message": "hello?"})
        assert resp.status_code == 404

    def test_full_interview_over_http(self, client) -> None:
        start = client.post(
            "/api/interview",
            json={"sessionId": "api-full", "candidate": _candidate().model_dump(mode="json")},
        )
        assert start.status_code == 200
        assert start.json()["done"] is False

        done = False
        for _ in range(20):
            resp = client.post(
                "/api/interview",
                json={
                    "sessionId": "api-full",
                    "message": "I can explain that, though I would need a moment to think.",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["reply"]
            if body["done"]:
                feedback = body["feedback"]
                assert feedback is not None
                assert feedback["summary"]
                assert isinstance(feedback["strengths"], list)
                done = True
                break
        assert done is True
