"""End-to-end personalization regression tests against the REAL curriculum.

Covers the four real candidate profiles shipped in ``frontend/src/data/candidates.ts``
(``candidate-001..004``) interviewed against the real ``app/data/curriculum.json``
(4 topics / 52 questions), in production mode. Verifies that:

1. the same candidate + curriculum always yields the same 8-question plan
   (deterministic, no random selection);
2. different candidates produce different plans where their profiles support
   it, and the plans stay grounded in the curriculum;
3. topic ranking reflects each candidate's declared profile signals;
4. every pair of candidate plans is reported with an overlap (Jaccard) score;
5. sessions are isolated and a fully-completed candidate A's answers,
   evaluations, feedback, messages and scores never appear in candidate B's
   session (or vice versa).

The ``TestPersonalizationReport`` class prints the per-candidate report; run
with ``-s`` to see it.
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
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator
from app.services.gemini_service import GeminiService
from app.services.interview_engine import InterviewEngine
from app.services.memory_engine import MemoryEngine
from app.services.question_planner import MIN_QUESTIONS, MIN_TOPICS, QuestionPlanner
from app.services.session_manager import SessionManager
from app.utils.config import Settings

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"
REAL_CURRICULUM_ID = "curriculum-001"

#: Question ids that ``candidate-001..004`` are expected to receive in order.
#: Pinned as the deterministic personalization contract for the shipped
#: curriculum. Plans are seeded per candidate id, so every candidate draws a
#: distinct deck from the 52-question bank even when their profiles overlap,
#: and the seeded rotation keeps the two systems-first candidates (001 and 004)
#: from colliding on the shared easy core.
#: Change these only when the curriculum or planner intent changes.
EXPECTED_QUESTION_IDS = {
    "candidate-001": ["sd-002", "db-004", "py-004", "al-001", "sd-007", "db-003", "sd-010", "sd-013"],
    "candidate-002": ["py-003", "db-004", "sd-003", "al-008", "py-004", "db-001", "py-006", "py-002"],
    "candidate-003": ["py-003", "db-001", "al-001", "sd-011", "py-001", "db-011", "py-005", "py-008"],
    "candidate-004": ["sd-011", "py-003", "db-009", "al-002", "sd-003", "py-001", "sd-012", "sd-001"],
}

#: Expected topic ranking (highest score first) per candidate.
EXPECTED_RANKED_TOPICS = {
    "candidate-001": ["topic-systems", "topic-databases", "topic-python", "topic-algorithms"],
    "candidate-002": ["topic-python", "topic-databases", "topic-systems", "topic-algorithms"],
    "candidate-003": ["topic-python", "topic-databases", "topic-algorithms", "topic-systems"],
    "candidate-004": ["topic-systems", "topic-python", "topic-databases", "topic-algorithms"],
}


def _candidates() -> dict[str, CandidateProfile]:
    """The four real candidate profiles, mirrored from ``frontend/src/data/candidates.ts``."""
    return {
        "candidate-001": CandidateProfile(
            id="candidate-001",
            name="Alex Rivera",
            role="Backend Engineer",
            years_of_experience=2.0,
            skills=[
                SkillLevel(name="Python", level="intermediate"),
                SkillLevel(name="SQL", level="beginner"),
                SkillLevel(name="Django", level="intermediate"),
                SkillLevel(name="Docker", level="beginner"),
                SkillLevel(name="System Design", level="beginner"),
            ],
            learning_journey=[
                {"type": "course", "title": "Python for Everybody", "description": "Intro Python course."},
                {"type": "project", "title": "RESTful Blog API", "description": "Django REST API with SQLite."},
                {"type": "practice", "title": "LeetCode / Codewars", "description": "Algorithm practice."},
            ],
            preferred_languages=["Python", "JavaScript"],
            focus_areas=["Backend API design", "Databases", "Testing"],
            notes="Prefers practical examples over theory; learning SQL depth and system design next.",
        ),
        "candidate-002": CandidateProfile(
            id="candidate-002",
            name="Ava Thompson",
            role="Frontend Engineer",
            years_of_experience=1.5,
            skills=[
                SkillLevel(name="JavaScript", level="intermediate"),
                SkillLevel(name="React", level="intermediate"),
                SkillLevel(name="TypeScript", level="beginner"),
                SkillLevel(name="CSS", level="advanced"),
            ],
            learning_journey=[
                {"type": "course", "title": "The Odin Project", "description": "HTML, CSS, and ES6."},
                {"type": "project", "title": "Dashboard UI", "description": "React dashboard."},
                {"type": "practice", "title": "Frontend Mentor", "description": "Responsive layout and a11y."},
            ],
            preferred_languages=["JavaScript", "TypeScript"],
            focus_areas=["Component architecture", "Accessibility", "State management"],
            notes="Strong on visual detail and CSS; learning TypeScript and testing next.",
        ),
        "candidate-003": CandidateProfile(
            id="candidate-003",
            name="Leo Park",
            role="Data Engineer",
            years_of_experience=3.0,
            skills=[
                SkillLevel(name="Python", level="advanced"),
                SkillLevel(name="SQL", level="intermediate"),
                SkillLevel(name="Spark", level="beginner"),
                SkillLevel(name="Airflow", level="beginner"),
            ],
            learning_journey=[
                {"type": "course", "title": "Data Engineering Zoomcamp", "description": "Batch/streaming pipelines."},
                {"type": "project", "title": "ELT Pipeline", "description": "ELT with dbt."},
                {"type": "book", "title": "Designing Data-Intensive Applications", "description": "Distributed systems."},
            ],
            preferred_languages=["Python", "SQL"],
            focus_areas=["Data pipelines", "Warehousing", "Streaming"],
            notes="Comfortable with pandas and SQL; learning Spark and streaming next.",
        ),
        "candidate-004": CandidateProfile(
            id="candidate-004",
            name="Maya Chen",
            role="Full-Stack Engineer",
            years_of_experience=4.0,
            skills=[
                SkillLevel(name="Python", level="advanced"),
                SkillLevel(name="React", level="intermediate"),
                SkillLevel(name="Node.js", level="intermediate"),
                SkillLevel(name="Docker", level="beginner"),
            ],
            learning_journey=[
                {"type": "project", "title": "E-commerce Platform", "description": "Django API + React client."},
                {"type": "course", "title": "System Design Primer", "description": "Scalability and reliability."},
                {"type": "practice", "title": "LeetCode", "description": "Algorithm practice."},
            ],
            preferred_languages=["Python", "JavaScript"],
            focus_areas=["API design", "Reliability", "Performance"],
            notes="Solid full-stack foundation; learning distributed systems and container orchestration next.",
        ),
    }


def _build_stack(tmp_path: Path) -> SimpleNamespace:
    """Wire every engine collaborator against the REAL curriculum + a temp DB."""
    db = Database(tmp_path / "interview.db")
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
    curriculum_loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
    candidate_analyzer = CandidateAnalyzer(data_dir=REAL_DATA_DIR)
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
        memory=memory_engine,
        message_repo=message_repo,
        score_repo=score_repo,
        feedback_repo=feedback_repo,
        curriculum=curriculum_loader.load_curriculum(REAL_CURRICULUM_ID),
    )


@pytest.fixture()
def stack(tmp_path: Path) -> SimpleNamespace:
    """The standard wired interview stack against the real curriculum."""
    return _build_stack(tmp_path)


# --- Helpers ----------------------------------------------------------------


def _questions(stack: SimpleNamespace, session_id: str) -> list[dict]:
    return stack.session_manager.get_session(session_id).context["plan"]["questions"]


def _context(stack: SimpleNamespace, session_id: str) -> dict:
    return stack.session_manager.get_session(session_id).context


def _full_answer(question: dict, marker: str = "") -> str:
    text = "I can explain this. " + ", ".join(question["expects"]) + " are all important concepts."
    return f"{marker}{text}"


def _drive_to_done(stack: SimpleNamespace, session_id: str, candidate: CandidateProfile, marker: str):
    resp = stack.engine.start(session_id, candidate)
    while not resp.done:
        resp = stack.engine.handle_answer(session_id, _full_answer(_context(stack, session_id)["current"], marker))
    return resp


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right)


def _distribution(question_ids: list[str], curriculum) -> dict[str, int]:
    id_to_topic = {q.id: topic.id for topic in curriculum.topics for q in topic.questions}
    dist: dict[str, int] = {}
    for question_id in question_ids:
        topic = id_to_topic[question_id]
        dist[topic] = dist.get(topic, 0) + 1
    return dist


def _plans_for_all(stack: SimpleNamespace) -> dict[str, object]:
    """Build a production-mode plan for every real candidate."""
    plans = {}
    for candidate_id, profile in _candidates().items():
        analysis = stack.candidate_analyzer.analyze_profile(profile)
        plans[candidate_id] = stack.planner.plan_for(analysis, stack.curriculum)
    return plans


# --- 1. Deterministic, grounded plans for every real candidate ---------------


class TestRealCurriculumPlans:
    def test_every_candidate_gets_a_complete_grounded_plan(
        self, stack: SimpleNamespace
    ) -> None:
        supplied_ids = {q.id for topic in stack.curriculum.topics for q in topic.questions}
        for candidate_id, plan in _plans_for_all(stack).items():
            assert plan.total_questions == MIN_QUESTIONS == 8
            assert plan.is_complete is True
            assert len(set(plan.topics_covered)) >= MIN_TOPICS
            planned = [q.curriculum_question_id for q in plan.questions]
            assert len(planned) == len(set(planned)) == 8
            assert set(planned) <= supplied_ids
            for question in plan.questions:
                assert question.text
                assert question.expects

    def test_every_candidate_plan_is_deterministic(self, stack: SimpleNamespace) -> None:
        for candidate_id, profile in _candidates().items():
            analysis = stack.candidate_analyzer.analyze_profile(profile)
            first = stack.planner.plan_for(analysis, stack.curriculum)
            second = stack.planner.plan_for(analysis, stack.curriculum)
            assert first == second
            assert [q.curriculum_question_id for q in first.questions] == EXPECTED_QUESTION_IDS[candidate_id]

    def test_backend_and_frontend_candidate_001_plans_match(self, stack: SimpleNamespace) -> None:
        """``candidate.json`` (backend) and the frontend profile agree for candidate-001."""
        from_backend = stack.planner.create_plan("candidate-001", REAL_CURRICULUM_ID)
        profile = _candidates()["candidate-001"]
        analysis = stack.candidate_analyzer.analyze_profile(profile)
        from_frontend = stack.planner.plan_for(analysis, stack.curriculum)
        assert [q.curriculum_question_id for q in from_backend.questions] == [
            q.curriculum_question_id for q in from_frontend.questions
        ]


# --- 2/3. Differentiation and relevance --------------------------------------


class TestDifferentiationAndRelevance:
    def test_plans_differ_where_profiles_support_it(self, stack: SimpleNamespace) -> None:
        plans = _plans_for_all(stack)
        sets = {cid: {q.curriculum_question_id for q in plan.questions} for cid, plan in plans.items()}

        # Plans are seeded per candidate id, so every candidate draws a distinct
        # deck from the bank — no two shipped candidates coincide.
        coincident = {frozenset((a, b)) for a in sets for b in sets if a < b and sets[a] == sets[b]}
        assert coincident == set()
        assert len({tuple(sorted(q.curriculum_question_id for q in plan.questions)) for plan in plans.values()}) == 4

    def test_first_question_reflects_profile(self, stack: SimpleNamespace) -> None:
        plans = _plans_for_all(stack)
        assert plans["candidate-001"].questions[0].topic_id == "topic-systems"
        assert plans["candidate-004"].questions[0].topic_id == "topic-systems"
        assert plans["candidate-003"].questions[0].topic_id == "topic-python"

    def test_topic_ranking_matches_profile_signals(self, stack: SimpleNamespace) -> None:
        for candidate_id, profile in _candidates().items():
            analysis = stack.candidate_analyzer.analyze_profile(profile)
            ranked = [topic.id for topic in stack.planner._rank_topics(analysis, stack.curriculum.topics)]
            assert ranked == EXPECTED_RANKED_TOPICS[candidate_id]

    def test_selected_questions_are_distributed_over_ranked_topics(
        self, stack: SimpleNamespace
    ) -> None:
        plans = _plans_for_all(stack)
        # Systems-first candidates concentrate on systems; python-first on python.
        assert _distribution(EXPECTED_QUESTION_IDS["candidate-001"], stack.curriculum)["topic-systems"] >= 3
        assert _distribution(EXPECTED_QUESTION_IDS["candidate-003"], stack.curriculum)["topic-python"] >= 4
        assert _distribution(EXPECTED_QUESTION_IDS["candidate-004"], stack.curriculum)["topic-systems"] >= 3


# --- 4. Pairwise overlap report ----------------------------------------------


class TestOverlapReport:
    def test_pairwise_overlap_matrix(self, stack: SimpleNamespace) -> None:
        plans = _plans_for_all(stack)
        sets = {cid: {q.curriculum_question_id for q in plan.questions} for cid, plan in plans.items()}

        assert sets["candidate-001"] & sets["candidate-002"] == {"db-004", "py-004"}
        assert sets["candidate-001"] & sets["candidate-003"] == {"al-001"}
        assert sets["candidate-001"] & sets["candidate-004"] == set()
        assert sets["candidate-002"] & sets["candidate-004"] == {"py-003", "sd-003"}
        assert sets["candidate-003"] & sets["candidate-004"] == {"py-001", "py-003", "sd-011"}

        # Overlap magnitudes: seeded rotation keeps each candidate's topic
        # emphasis while shrinking the shared easy core, so the two
        # systems-first candidates (001 and 004) no longer collide at all.
        assert _jaccard(sets["candidate-001"], sets["candidate-004"]) < _jaccard(
            sets["candidate-001"], sets["candidate-002"]
        )
        assert round(_jaccard(sets["candidate-002"], sets["candidate-003"]), 2) == round(2 / 14, 2)


# --- 5. Cross-candidate session isolation ------------------------------------


class TestCrossCandidateLeakage:
    def test_completed_candidate_a_never_leaks_into_candidate_b(
        self, stack: SimpleNamespace
    ) -> None:
        candidates = _candidates()
        _drive_to_done(stack, "sess-a", candidates["candidate-001"], marker="SECRET-A")

        # A completed with evaluations, scores, messages and a feedback report.
        a_feedback = stack.feedback_repo.get_by_session("sess-a")
        assert a_feedback is not None
        assert stack.score_repo.list_by_session("sess-a")
        a_transcript = stack.memory.get_conversation_history("sess-a")
        assert all(message["session_id"] == "sess-a" for message in a_transcript)
        assert any("SECRET-A" in message["content"] for message in a_transcript)

        # B is a different candidate in a separate session, still at question one.
        stack.engine.start("sess-b", candidates["candidate-002"])
        context_b = _context(stack, "sess-b")
        assert context_b["analysis"]["candidate_id"] == "candidate-002"
        assert context_b["plan"]["candidate_id"] == "candidate-002"
        assert context_b["answers"] == []
        assert context_b["evaluations"] == []
        assert context_b["follow_ups"] == []
        assert context_b["primary_answered"] == 0

        # Nothing from A is observable from B's session across every store.
        assert stack.memory.get_previous_answers("sess-b") == []
        assert stack.memory.get_evaluations("sess-b") == []
        assert stack.memory.get_missing_concepts("sess-b") == []
        assert stack.score_repo.list_by_session("sess-b") == []
        assert stack.feedback_repo.get_by_session("sess-b") is None
        b_transcript = stack.memory.get_conversation_history("sess-b")
        assert all(message["session_id"] == "sess-b" for message in b_transcript)
        assert all("SECRET-A" not in message["content"] for message in b_transcript)
        assert b_transcript[0]["content"].startswith("Welcome, Ava Thompson!")
        assert "SECRET-A" not in json.dumps(context_b)
        assert "SECRET-A" not in json.dumps(stack.memory.get_recent("sess-b"))

    def test_candidate_b_answers_do_not_affect_completed_candidate_a(
        self, stack: SimpleNamespace
    ) -> None:
        candidates = _candidates()
        _drive_to_done(stack, "sess-a", candidates["candidate-001"], marker="SECRET-A")
        a_feedback_before = stack.feedback_repo.get_by_session("sess-a")

        stack.engine.start("sess-b", candidates["candidate-002"])
        first_b = _context(stack, "sess-b")["current"]
        stack.engine.handle_answer("sess-b", _full_answer(first_b, marker="SECRET-B"))

        # B's answer lives only in B's session.
        assert [a["answer"] for a in stack.memory.get_previous_answers("sess-b")] == [
            "SECRET-B" + _full_answer(first_b)
        ]
        assert all("SECRET-B" not in a["answer"] for a in stack.memory.get_previous_answers("sess-a"))
        assert all("SECRET-B" not in m["content"] for m in stack.memory.get_conversation_history("sess-a"))
        assert all("SECRET-A" not in m["content"] for m in stack.memory.get_conversation_history("sess-b"))

        # A's completed report is untouched.
        assert stack.feedback_repo.get_by_session("sess-a") == a_feedback_before


# --- Debug report (run with -s) ----------------------------------------------


class TestPersonalizationReport:
    def test_report_all_candidates(self, stack: SimpleNamespace) -> None:
        """Prints the per-candidate personalization report (pytest -s)."""
        plans = {}
        for candidate_id, profile in _candidates().items():
            analysis = stack.candidate_analyzer.analyze_profile(profile)
            ranked = stack.planner._rank_topics(analysis, stack.curriculum.topics)
            plan = stack.planner.plan_for(analysis, stack.curriculum)
            plans[candidate_id] = plan

            print(f"\n== {candidate_id} | {profile.name} | {profile.role} ==")
            print("  ranked topics:", " > ".join(topic.id for topic in ranked))
            print(f"  distribution:  {_distribution([q.curriculum_question_id for q in plan.questions], stack.curriculum)}")
            for question in plan.questions:
                print(f"    {question.sequence}. [{question.topic_id}] {question.curriculum_question_id} ({question.difficulty}): {question.text}")

        sets = {cid: {q.curriculum_question_id for q in plan.questions} for cid, plan in plans.items()}
        print("\n== pairwise overlap (Jaccard) ==")
        for a in sets:
            for b in sets:
                if a >= b:
                    continue
                print(f"  {a} vs {b}: {_jaccard(sets[a], sets[b]):.2f}")
