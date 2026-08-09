"""Question-bank and custom-profile interview tests.

Guards the two behavioral contracts the UI depends on:

1. **Question bank semantics.** The shipped curriculum (``curriculum-001``) is a
   question *bank* of 52 grounded questions. A single interview must ask exactly
   ``MIN_QUESTIONS`` (8) primary questions, never the whole bank, never repeat a
   question, and cover at least ``MIN_TOPICS`` (4) topics. Follow-up questions
   deepen the current primary — they must not be counted as new primary
   questions and must not lengthen the interview.

2. **Custom profile pipeline.** A user-created profile (``custom-`` id prefix)
   posted to ``POST /api/interview`` flows through the same
   CandidateAnalyzer -> QuestionPlanner -> InterviewEngine pipeline as a
   predefined candidate, produces a personalized 8-question plan, and honors the
   experience-level difficulty bias (junior -> easy, senior -> hard, mid ->
   balanced). Predefined candidates keep their pinned deterministic plans.

Engine-level tests cover both; API-level tests exercise the wire contract and
are skipped when httpx is unavailable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.candidate import CandidateProfile, SkillLevel
from app.services.question_planner import MIN_QUESTIONS, MIN_TOPICS
from app.utils.config import Settings

from tests.test_personalization_e2e import EXPECTED_QUESTION_IDS, _build_stack, _candidates

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"

#: The full shipped bank size — guards that the "never the whole bank" asserts
#: are actually exercised against a 52-question curriculum.
BANK_SIZE = 52


def _custom_profile(
    name: str,
    role: str,
    experience_level: str,
    *,
    skills: list[tuple[str, str]],
    focus_areas: list[str],
    projects: list[str] = (),
    languages: list[str] = (),
) -> CandidateProfile:
    """A profile exactly as ``buildCustomProfile`` (frontend) would produce it."""
    years = {"junior": 1, "mid": 3, "senior": 6}.get(experience_level, 3)
    return CandidateProfile(
        id=f"custom-{name.lower().replace(' ', '-')}",
        name=name,
        role=role,
        experience_level=experience_level,
        years_of_experience=float(years),
        skills=[SkillLevel(name=name_, level=level) for name_, level in skills],
        learning_journey=[{"type": "project", "title": title, "description": ""} for title in projects],
        preferred_languages=list(languages),
        focus_areas=list(focus_areas),
        notes="",
    )


def _bank_question_ids(stack) -> set[str]:
    return {q.id for topic in stack.curriculum.topics for q in topic.questions}


def _context(stack, session_id: str) -> dict:
    return stack.session_manager.get_session(session_id).context


def _current(stack, session_id: str) -> dict:
    return _context(stack, session_id)["current"]


def _weak_answer(_question: dict) -> str:
    return "I'm not sure about this one."


def _full_answer(question: dict) -> str:
    return "I can explain this. " + ", ".join(question["expects"]) + " are all important concepts."


def _drive_to_done(stack, candidate: CandidateProfile, responder, session_id: str):
    resp = stack.engine.start(session_id, candidate)
    while not resp.done:
        resp = stack.engine.handle_answer(session_id, responder(_current(stack, session_id)))
    return resp


@pytest.fixture()
def stack(tmp_path: Path):
    """The real-curriculum interview stack (mirrors test_personalization_e2e)."""
    return _build_stack(tmp_path)


# --- Question bank semantics -------------------------------------------------


class TestQuestionBankSemantics:
    def test_fixture_is_the_full_bank(self, stack) -> None:
        """Sanity guard: the curriculum really is the 52-question bank."""
        assert BANK_SIZE == len(_bank_question_ids(stack)) == 52
        assert len(stack.curriculum.topics) == 4

    def test_full_session_asks_exactly_min_questions_never_the_bank(
        self, stack, candidate_id: str = "candidate-001"
    ) -> None:
        candidate = _candidates()[candidate_id]
        _drive_to_done(stack, candidate, _weak_answer, session_id="bank-full")

        context = _context(stack, "bank-full")
        asked = [q["curriculum_question_id"] for q in context["asked_questions"]]
        assert len(context["plan"]["questions"]) == MIN_QUESTIONS == 8
        assert len(asked) == MIN_QUESTIONS == 8
        # The 52-question bank is never dumped wholesale into one interview.
        assert set(asked) != _bank_question_ids(stack)

    def test_no_question_repeats_within_a_session(self, stack) -> None:
        candidate = _candidates()["candidate-001"]
        _drive_to_done(stack, candidate, _weak_answer, session_id="bank-unique")

        context = _context(stack, "bank-unique")
        asked = [q["curriculum_question_id"] for q in context["asked_questions"]]
        planned = [q["curriculum_question_id"] for q in context["plan"]["questions"]]
        assert len(asked) == len(set(asked)) == 8
        assert len(planned) == len(set(planned)) == 8
        # Every asked primary is drawn from the plan; nothing is invented.
        assert set(asked) == set(planned)
        assert set(asked) <= _bank_question_ids(stack)

    def test_at_least_min_topics_covered(self, stack) -> None:
        _drive_to_done(stack, _candidates()["candidate-001"], _weak_answer, session_id="bank-topics")
        covered = set(_context(stack, "bank-topics")["topics_covered"])
        assert len(covered) >= MIN_TOPICS == 4

    def test_follow_ups_do_not_increment_primary_count(self, stack) -> None:
        """A weak answer triggers follow-ups that never add primary questions."""
        _drive_to_done(stack, _candidates()["candidate-001"], _weak_answer, session_id="bank-fu")

        context = _context(stack, "bank-fu")
        # Exactly 8 primaries were answered; follow-ups are counted separately.
        assert context["primary_question_count"] == MIN_QUESTIONS == 8
        assert context["follow_up_count"] >= 1
        # Follow-ups never show up as (primary) asked questions, so the visible
        # primary question list is still exactly the 8-question plan.
        assert len(context["asked_questions"]) == MIN_QUESTIONS == 8
        assert context["primary_index"] == MIN_QUESTIONS - 1

    def test_two_sessions_for_same_candidate_do_not_share_state(self, stack) -> None:
        candidate = _candidates()["candidate-001"]
        _drive_to_done(stack, candidate, _weak_answer, session_id="bank-a")

        resp = stack.engine.start("bank-b", candidate)
        assert resp.done is False
        context_b = _context(stack, "bank-b")
        assert context_b["primary_question_count"] == 0
        assert context_b["follow_up_count"] == 0
        assert len(context_b["asked_questions"]) == 1
        assert context_b["primary_index"] == 0


# --- Custom profile pipeline -------------------------------------------------


class TestCustomProfilePipeline:
    def test_custom_profile_starts_over_api(self, stack) -> None:
        client = _api_client(stack)
        profile = _custom_profile(
            "Riley Doe",
            "Backend Developer",
            "mid",
            skills=[("Python", "advanced"), ("FastAPI", "intermediate"), ("SQL", "intermediate")],
            focus_areas=["Backend API design", "Databases", "Testing"],
            projects=["RESTful Blog API"],
            languages=["Python"],
        )
        resp = client.post(
            "/api/interview",
            json={"sessionId": "custom-1", "candidate": profile.model_dump(mode="json")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["done"] is False
        assert body["feedback"] is None
        assert "Welcome, Riley Doe!" in body["reply"]
        assert "8 questions" in body["reply"]

        context = _context(stack, "custom-1")
        assert context["plan"]["candidate_id"] == "custom-riley-doe"
        assert context["analysis"]["candidate_id"] == "custom-riley-doe"

    def test_custom_profile_plan_is_capped_grounded_and_varied(self, stack) -> None:
        profile = _custom_profile(
            "Riley Doe",
            "Backend Developer",
            "mid",
            skills=[("Python", "advanced"), ("FastAPI", "intermediate"), ("SQL", "intermediate")],
            focus_areas=["Backend API design", "Databases", "Testing"],
            projects=["RESTful Blog API"],
            languages=["Python"],
        )
        stack.engine.start("custom-plan", profile)
        context = _context(stack, "custom-plan")
        plan = context["plan"]
        asked = {q["curriculum_question_id"] for q in plan["questions"]}
        assert plan["total_questions"] == MIN_QUESTIONS == 8
        assert len(asked) == 8
        assert asked <= _bank_question_ids(stack)
        assert asked != _bank_question_ids(stack)
        assert len({q["topic_id"] for q in plan["questions"]}) >= MIN_TOPICS

    def test_custom_profile_difficulty_bias(self, stack) -> None:
        def bias(profile: CandidateProfile, session_id: str) -> str | None:
            stack.engine.start(session_id, profile)
            return _context(stack, session_id)["plan"]["difficulty_bias"]

        junior = _custom_profile(
            "Juno Bee", "Backend Developer", "junior",
            skills=[("Python", "beginner"), ("SQL", "beginner")],
            focus_areas=["Databases"],
        )
        senior = _custom_profile(
            "Sonia Fox", "Staff Engineer", "senior",
            skills=[("Python", "advanced"), ("SQL", "advanced"), ("System Design", "advanced")],
            focus_areas=["System Design", "Performance"],
        )
        mid = _custom_profile(
            "Milo Gray", "Backend Developer", "mid",
            skills=[("Python", "intermediate")],
            focus_areas=["Backend API design"],
        )
        assert bias(junior, "custom-bias-junior") == "easy"
        assert bias(senior, "custom-bias-senior") == "hard"
        assert bias(mid, "custom-bias-mid") is None

    def test_unknown_experience_level_stays_balanced(self, stack) -> None:
        profile = _custom_profile(
            "Pat Lee", "Developer", "staff",
            skills=[("Python", "advanced")],
            focus_areas=["Backend API design"],
        )
        stack.engine.start("custom-unknown", profile)
        assert _context(stack, "custom-unknown")["plan"]["difficulty_bias"] is None

    def test_predefined_candidates_stay_balanced(self, stack) -> None:
        for candidate_id, profile in _candidates().items():
            stack.engine.start(f"custom-predef-{candidate_id}", profile)
            assert _context(stack, f"custom-predef-{candidate_id}")["plan"]["difficulty_bias"] is None

    def test_different_custom_profiles_yield_different_plans(self, stack) -> None:
        backend = _custom_profile(
            "Riley Doe", "Backend Developer", "senior",
            skills=[("Python", "advanced"), ("FastAPI", "intermediate"), ("SQL", "intermediate")],
            focus_areas=["Backend API design", "Databases", "Testing"],
            projects=["RESTful Blog API"],
            languages=["Python"],
        )
        data = _custom_profile(
            "Noor Ali", "Data Engineer", "mid",
            skills=[("SQL", "intermediate"), ("Spark", "intermediate"), ("Airflow", "beginner")],
            focus_areas=["Data pipelines", "Warehousing"],
            projects=["ELT Pipeline"],
            languages=["SQL"],
        )
        stack.engine.start("custom-backend", backend)
        stack.engine.start("custom-data", data)
        backend_ids = {q["curriculum_question_id"] for q in _context(stack, "custom-backend")["plan"]["questions"]}
        data_ids = {q["curriculum_question_id"] for q in _context(stack, "custom-data")["plan"]["questions"]}
        assert len(backend_ids) == len(data_ids) == 8
        assert backend_ids != data_ids
        # Both stay grounded in the bank.
        assert backend_ids <= _bank_question_ids(stack)
        assert data_ids <= _bank_question_ids(stack)

    def test_custom_profile_full_interview_over_http(self, stack) -> None:
        client = _api_client(stack)
        profile = _custom_profile(
            "Riley Doe", "Backend Developer", "mid",
            skills=[("Python", "advanced"), ("FastAPI", "intermediate")],
            focus_areas=["Backend API design"],
            projects=["RESTful Blog API"],
            languages=["Python"],
        )
        start = client.post(
            "/api/interview",
            json={"sessionId": "custom-http", "candidate": profile.model_dump(mode="json")},
        )
        assert start.status_code == 200

        done = False
        for _ in range(30):
            resp = client.post(
                "/api/interview",
                json={"sessionId": "custom-http", "message": "I'm not sure about this one."},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["reply"]
            if body["done"]:
                assert body["feedback"] is not None
                assert body["feedback"]["summary"]
                done = True
                break
        assert done is True

        context = _context(stack, "custom-http")
        assert context["primary_question_count"] == MIN_QUESTIONS == 8
        assert context["follow_up_count"] >= 1
        assert len({q["curriculum_question_id"] for q in context["asked_questions"]}) == 8

    def test_predefined_candidate_api_plan_matches_pinned_contract(self, stack) -> None:
        """Regression: the API path still returns candidate-001's pinned plan.

        Decks are seeded per session (``<candidate_id>:<session_id>``) so every
        interview draws a fresh question set; this pins the deterministic deck
        the API must return for the ``custom-pinned`` session.
        """
        client = _api_client(stack)
        profile = _candidates()["candidate-001"]
        resp = client.post(
            "/api/interview",
            json={"sessionId": "custom-pinned", "candidate": profile.model_dump(mode="json")},
        )
        assert resp.status_code == 200
        plan_ids = [q["curriculum_question_id"] for q in _context(stack, "custom-pinned")["plan"]["questions"]]
        assert plan_ids == [
            "sd-011", "db-009", "py-011", "al-011", "sd-007", "db-003", "sd-006", "sd-001",
        ]

    def test_same_profile_gets_a_fresh_deck_in_a_new_session(self, stack) -> None:
        """Re-running the same candidate profile re-draws the deck per session."""
        profile = _candidates()["candidate-001"]
        stack.engine.start("fresh-deck-1", profile)
        stack.engine.start("fresh-deck-2", profile)
        first = [q["curriculum_question_id"] for q in _context(stack, "fresh-deck-1")["plan"]["questions"]]
        second = [q["curriculum_question_id"] for q in _context(stack, "fresh-deck-2")["plan"]["questions"]]
        assert len(first) == len(second) == 8
        assert first != second


def _api_client(stack):
    pytest.importorskip("httpx")
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
