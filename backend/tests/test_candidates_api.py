"""Tests for candidate persistence, history, reports, and PDF export.

Uses a temp SQLite database plus the real ``candidates.json`` seed data and the
FastAPI TestClient (skipped when httpx is unavailable).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database.connection import Database
from app.database.repositories.candidate_repository import CandidateRepository
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.models.common import utc_now
from app.models.candidate import CandidateCreate
from app.models.session import SessionCreate
from app.services.candidate_seeder import CandidateSeeder
from app.services.report_service import ReportService
from app.services.session_manager import SessionManager

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"


def _stack(tmp_path: Path) -> SimpleNamespace:
    """Build repositories + report service against a temp database."""
    db = Database(tmp_path / "candidates.db")
    db.initialize()
    candidates = CandidateRepository(db)
    sessions = SessionRepository(db)
    messages = MessageRepository(db)
    feedback = FeedbackRepository(db)
    scores = ScoreRepository(db)
    report = ReportService(
        candidate_repository=candidates,
        session_repository=sessions,
        message_repository=messages,
        feedback_repository=feedback,
        score_repository=scores,
    )
    return SimpleNamespace(
        db=db,
        candidates=candidates,
        sessions=sessions,
        messages=messages,
        feedback=feedback,
        scores=scores,
        report=report,
    )


def _seed(stack: SimpleNamespace, data_dir: Path = REAL_DATA_DIR) -> int:
    return CandidateSeeder(stack.candidates, data_dir=data_dir).seed()


def _client(stack: SimpleNamespace):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import (
        get_candidate_repository,
        get_report_service,
        get_session_repository,
    )
    from app.api.middleware import setup_error_handlers
    from app.api.routes.candidates import router

    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_candidate_repository] = lambda: stack.candidates
    app.dependency_overrides[get_session_repository] = lambda: stack.sessions
    app.dependency_overrides[get_report_service] = lambda: stack.report
    return TestClient(app)


def _make_completed_session(stack: SimpleNamespace, session_id: str, candidate_id: str) -> None:
    """Create + complete a session and persist a feedback report for it."""
    manager = SessionManager(stack.sessions)
    manager.create_session(
        SessionCreate(candidate_id=candidate_id, curriculum_id="curriculum-001"),
        session_id=session_id,
    )
    stack.sessions.update_state(session_id, "COMPLETED", completed_at=utc_now())
    stack.feedback.create(
        feedback_id=f"fb-{session_id}",
        session_id=session_id,
        overall_score=8.5,
        summary="Solid interview.",
        strengths=["Python (intermediate)"],
        improvements=["System Design (beginner)"],
        topics=[
            {
                "topic_id": "topic-python",
                "title": "Python Fundamentals",
                "average_score": 8.5,
                "strengths": [],
                "improvements": [],
            }
        ],
        created_at=utc_now(),
    )
    stack.messages.create(
        message_id=f"msg-{session_id}-1",
        session_id=session_id,
        role="interviewer",
        content="What is a list comprehension?",
        metadata={"kind": "question"},
        created_at=utc_now(),
    )


def _candidate_payload(**overrides) -> dict:
    payload = {
        "name": "Riley Doe",
        "email": "riley.doe@example.com",
        "role": "Backend Developer",
        "years_of_experience": 3.0,
        "experience_level": "mid",
        "skills": [{"name": "Python", "level": "intermediate"}],
        "learning_journey": [],
        "preferred_languages": ["Python"],
        "focus_areas": ["Backend API design"],
        "strengths": ["Python (intermediate)"],
        "notes": "",
    }
    payload.update(overrides)
    return payload


class TestSeeding:
    def test_seed_creates_all_predefined_candidates(self, tmp_path: Path) -> None:
        stack = _stack(tmp_path)
        count = _seed(stack)
        assert count == 4
        rows = stack.candidates.list_all()
        assert len(rows) == 4
        ids = {row["id"] for row in rows}
        assert ids == {f"candidate-00{i}" for i in range(1, 5)}
        assert all(row["email"] for row in rows)

    def test_seed_is_idempotent(self, tmp_path: Path) -> None:
        stack = _stack(tmp_path)
        _seed(stack)
        _seed(stack)
        assert len(stack.candidates.list_all()) == 4

    def test_seed_preserves_custom_overrides(self, tmp_path: Path) -> None:
        stack = _stack(tmp_path)
        _seed(stack)
        stack.candidates.upsert(
            candidate_id="candidate-001",
            name="Renamed Candidate",
            email="custom@example.com",
            role="Data Engineer",
            years_of_experience=5.0,
            experience_level="senior",
            skills=[],
            learning_journey=[],
            preferred_languages=[],
            focus_areas=[],
            strengths=[],
            notes="",
            now=utc_now(),
        )
        _seed(stack)
        row = stack.candidates.get_by_id("candidate-001")
        assert row["name"] == "Renamed Candidate"
        assert row["email"] == "custom@example.com"


class TestCandidatesApi:
    @pytest.fixture()
    def stack(self, tmp_path: Path) -> SimpleNamespace:
        return _stack(tmp_path)

    @pytest.fixture()
    def client(self, stack: SimpleNamespace):
        pytest.importorskip("httpx")
        return _client(stack)

    def test_list_candidates_returns_seeded_rows(self, client, stack) -> None:
        _seed(stack)
        resp = client.get("/api/candidates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 4
        assert {item["id"] for item in body["items"]} == {f"candidate-00{i}" for i in range(1, 5)}
        first = body["items"][0]
        assert "email" in first
        assert "strengths" in first

    def test_create_candidate_returns_201_with_custom_id(self, client, stack) -> None:
        resp = client.post("/api/candidates", json=_candidate_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"].startswith("custom-")
        assert body["email"] == "riley.doe@example.com"
        assert body["strengths"] == ["Python (intermediate)"]

    def test_create_candidate_with_same_email_updates_in_place(self, client, stack) -> None:
        first = client.post("/api/candidates", json=_candidate_payload())
        assert first.status_code == 201
        created_id = first.json()["id"]

        second = client.post(
            "/api/candidates",
            json=_candidate_payload(name="Riley Updated", years_of_experience=4.0),
        )
        assert second.status_code == 200
        body = second.json()
        assert body["id"] == created_id
        assert body["name"] == "Riley Updated"
        assert body["years_of_experience"] == 4.0
        assert len(stack.candidates.list_all()) == 1

    def test_create_candidate_rejects_bad_email(self, client, stack) -> None:
        resp = client.post("/api/candidates", json=_candidate_payload(email="not-an-email"))
        assert resp.status_code == 422

    def test_create_candidate_rejects_missing_name(self, client, stack) -> None:
        resp = client.post("/api/candidates", json=_candidate_payload(name="  "))
        assert resp.status_code == 422


class TestHistoryAndReport:
    @pytest.fixture()
    def stack(self, tmp_path: Path) -> SimpleNamespace:
        return _stack(tmp_path)

    @pytest.fixture()
    def client(self, stack: SimpleNamespace):
        pytest.importorskip("httpx")
        return _client(stack)

    def test_history_lists_sessions_with_scores(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-1", "candidate-001")
        resp = client.get("/api/candidates/candidate-001/interviews")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["session_id"] == "sess-1"
        assert body["items"][0]["overall_score"] == 8.5
        assert body["items"][0]["summary"] == "Solid interview."

    def test_history_for_unknown_candidate_is_404(self, client, stack) -> None:
        resp = client.get("/api/candidates/nope/interviews")
        assert resp.status_code == 404

    def test_report_returns_feedback_candidate_and_messages(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-1", "candidate-001")
        resp = client.get("/api/candidates/candidate-001/interviews/sess-1/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "sess-1"
        assert body["candidate"]["name"] == "Alex Rivera"
        assert body["candidate"]["email"] == "alex.rivera@example.com"
        assert body["feedback"]["overall_score"] == 8.5
        assert body["feedback"]["summary"] == "Solid interview."
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "interviewer"

    def test_report_includes_answer_reviews(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-2", "candidate-001")
        now = utc_now()
        stack.messages.create(
            message_id="msg-2-q",
            session_id="sess-2",
            role="interviewer",
            content="How do Python list comprehensions work?",
            metadata={"kind": "question", "question_id": "py-001", "topic_id": "topic-python"},
            created_at=now,
        )
        stack.messages.create(
            message_id="msg-2-a",
            session_id="sess-2",
            role="candidate",
            content="They build a new list by applying an expression to each item.",
            metadata={"kind": "answer", "question_id": "py-001", "topic_id": "topic-python"},
            created_at=now,
        )
        stack.scores.create(
            score_id="score-2-good",
            session_id="sess-2",
            topic_id="topic-python",
            question_id="py-001",
            score=9.0,
            rationale="Covered the core concept well.",
            created_at=now,
        )
        stack.scores.create(
            score_id="score-2-bad",
            session_id="sess-2",
            topic_id="topic-python",
            question_id="py-002",
            score=4.0,
            rationale="Missing key details.",
            created_at=now,
        )
        resp = client.get("/api/candidates/candidate-001/interviews/sess-2/report")
        assert resp.status_code == 200
        reviews = resp.json()["answer_reviews"]
        assert len(reviews) == 2
        by_question = {r["question_id"]: r for r in reviews}
        good = by_question["py-001"]
        assert good["question"] == "How do Python list comprehensions work?"
        assert good["answer"] == "They build a new list by applying an expression to each item."
        assert good["score"] == 9.0
        assert good["verdict"] == "Very good"
        assert good["topic_title"] == "Python Fundamentals"
        assert by_question["py-002"]["verdict"] == "Needs improvement"

    def test_report_deduplicates_repeated_scores_for_a_question(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-3", "candidate-001")
        now = utc_now()
        stack.messages.create(
            message_id="msg-3-q",
            session_id="sess-3",
            role="interviewer",
            content="Explain indexes.",
            metadata={"kind": "question", "question_id": "db-001", "topic_id": "topic-python"},
            created_at=now,
        )
        stack.messages.create(
            message_id="msg-3-a",
            session_id="sess-3",
            role="candidate",
            content="Indexes speed up lookups.",
            metadata={"kind": "answer", "question_id": "db-001", "topic_id": "topic-python"},
            created_at=now,
        )
        for i, score in enumerate((3.0, 8.5)):
            stack.scores.create(
                score_id=f"score-3-{i}",
                session_id="sess-3",
                topic_id="topic-python",
                question_id="db-001",
                score=score,
                rationale=f"pass {i}",
                created_at=now,
            )
        resp = client.get("/api/candidates/candidate-001/interviews/sess-3/report")
        assert resp.status_code == 200
        reviews = resp.json()["answer_reviews"]
        assert len(reviews) == 1
        assert reviews[0]["score"] == 8.5

    def test_report_for_session_without_feedback_is_404(self, client, stack) -> None:
        _seed(stack)
        manager = SessionManager(stack.sessions)
        manager.create_session(
            SessionCreate(candidate_id="candidate-001", curriculum_id="curriculum-001"),
            session_id="sess-empty",
        )
        resp = client.get("/api/candidates/candidate-001/interviews/sess-empty/report")
        assert resp.status_code == 404

    def test_report_for_session_of_another_candidate_is_404(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-1", "candidate-001")
        resp = client.get("/api/candidates/candidate-002/interviews/sess-1/report")
        assert resp.status_code == 404

    def test_pdf_report_is_downloadable(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-1", "candidate-001")
        resp = client.get("/api/candidates/candidate-001/interviews/sess-1/report/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "content-disposition" in resp.headers
        assert resp.content.startswith(b"%PDF")

    def test_pdf_for_unknown_session_is_404(self, client, stack) -> None:
        _seed(stack)
        resp = client.get("/api/candidates/candidate-001/interviews/sess-nope/report/pdf")
        assert resp.status_code == 404

    def test_pdf_alias_resolves_candidate(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-1", "candidate-001")
        resp = client.get("/api/interviews/sess-1/report/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    def test_pdf_alias_unknown_session_is_404(self, client, stack) -> None:
        _seed(stack)
        resp = client.get("/api/interviews/sess-nope/report/pdf")
        assert resp.status_code == 404


class TestDelete:
    @pytest.fixture()
    def stack(self, tmp_path: Path) -> SimpleNamespace:
        return _stack(tmp_path)

    @pytest.fixture()
    def client(self, stack: SimpleNamespace):
        pytest.importorskip("httpx")
        return _client(stack)

    def test_list_marks_custom_and_default_candidates(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-1", "candidate-001")
        client.post("/api/candidates", json=_candidate_payload())
        resp = client.get("/api/candidates")
        assert resp.status_code == 200
        by_id = {item["id"]: item for item in resp.json()["items"]}
        assert by_id["candidate-001"]["is_custom"] is False
        assert by_id["candidate-002"]["is_custom"] is False
        custom = [item for item in by_id.values() if item["id"].startswith("custom-")]
        assert len(custom) == 1
        assert custom[0]["is_custom"] is True

    def test_delete_custom_candidate_removes_profile_and_sessions(self, client, stack) -> None:
        _seed(stack)
        created = client.post("/api/candidates", json=_candidate_payload()).json()
        candidate_id = created["id"]
        manager = SessionManager(stack.sessions)
        manager.create_session(
            SessionCreate(candidate_id=candidate_id, curriculum_id="curriculum-001"),
            session_id="sess-custom",
        )
        resp = client.delete(f"/api/candidates/{candidate_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["deleted_sessions"] == 1
        assert stack.candidates.get_by_id(candidate_id) is None
        assert stack.sessions.list_by_candidate(candidate_id) == []
        assert client.get(f"/api/candidates/{candidate_id}/interviews").status_code == 404

    def test_delete_default_candidate_is_forbidden(self, client, stack) -> None:
        _seed(stack)
        resp = client.delete("/api/candidates/candidate-001")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["code"] == "permission_denied"
        assert stack.candidates.get_by_id("candidate-001") is not None

    def test_delete_unknown_candidate_is_404(self, client, stack) -> None:
        _seed(stack)
        resp = client.delete("/api/candidates/custom-nope")
        assert resp.status_code == 404

    def test_clear_history_removes_sessions_but_keeps_candidate(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-1", "candidate-001")
        _make_completed_session(stack, "sess-2", "candidate-001")
        resp = client.delete("/api/candidates/candidate-001/interviews")
        assert resp.status_code == 200
        assert resp.json()["deleted_sessions"] == 2
        assert stack.candidates.get_by_id("candidate-001") is not None
        assert stack.sessions.list_by_candidate("candidate-001") == []
        assert client.get("/api/candidates/candidate-001/interviews").json()["total"] == 0

    def test_clear_history_cascades_messages_and_scores(self, client, stack) -> None:
        _seed(stack)
        _make_completed_session(stack, "sess-1", "candidate-001")
        now = utc_now()
        stack.scores.create(
            score_id="score-1",
            session_id="sess-1",
            topic_id="topic-python",
            question_id="py-001",
            score=9.0,
            rationale="ok",
            created_at=now,
        )
        client.delete("/api/candidates/candidate-001/interviews")
        with stack.db.connection() as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM scores").fetchone()["n"] == 0
            assert conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 0
            assert conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"] == 0

    def test_clear_history_unknown_candidate_is_404(self, client, stack) -> None:
        _seed(stack)
        resp = client.delete("/api/candidates/nope/interviews")
        assert resp.status_code == 404


class TestCandidateCreateModel:
    def test_model_round_trip(self) -> None:
        profile = CandidateCreate(**_candidate_payload())
        assert profile.email == "riley.doe@example.com"
        assert profile.skills[0].name == "Python"
