"""Focused tests for the QuestionPlanner service.

Uses a synthetic 5-topic curriculum fixture (13 grounded questions across easy /
medium / hard) plus constructed candidate analyses so personalization, skipped
topic handling, difficulty progression, and error paths are all deterministic.
The real shipped curriculum (4 topics / 40 questions) is used to verify that a
production-mode plan can be built against it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.models.candidate import CandidateAnalysis, CandidateProfile, SkillLevel
from app.models.curriculum import Curriculum, InterviewPlan, QuestionTemplate, Topic
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.question_planner import MIN_QUESTIONS, MIN_TOPICS, QuestionPlanner
from app.utils.config import Settings
from app.utils.errors import ValidationError

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"

#: Synthetic 5-topic curriculum with 13 grounded questions across all tiers.
CURRICULUM_PLAN = {
    "id": "curriculum-plan",
    "title": "Synthetic Interview Curriculum",
    "description": "Five topics with varied-difficulty questions for planner tests.",
    "version": "1.0.0",
    "topics": [
        {
            "id": "topic-python",
            "title": "Python Fundamentals",
            "description": "Data structures, comprehensions, typing, and common idioms.",
            "weight": 1.2,
            "questions": [
                {
                    "id": "py-e1",
                    "text": "Explain the difference between a list and a tuple.",
                    "difficulty": "easy",
                    "expects": ["immutable", "mutable", "performance"],
                },
                {
                    "id": "py-m1",
                    "text": "What is the difference between a list comprehension and a generator expression?",
                    "difficulty": "medium",
                    "expects": ["iterator", "lazy", "memory"],
                },
                {
                    "id": "py-h1",
                    "text": "How would you design a decorator that caches function results?",
                    "difficulty": "hard",
                    "expects": ["closure", "memoization", "lru cache"],
                },
            ],
        },
        {
            "id": "topic-databases",
            "title": "Databases & SQL",
            "description": "Relational modeling, indexing, and query performance.",
            "weight": 1.0,
            "questions": [
                {
                    "id": "db-e1",
                    "text": "Explain the differences between a primary key and a foreign key.",
                    "difficulty": "easy",
                    "expects": ["unique", "referential integrity", "relationship"],
                },
                {
                    "id": "db-m1",
                    "text": "How does a B-tree index speed up query lookups?",
                    "difficulty": "medium",
                    "expects": ["logarithmic", "tree structure", "selectivity"],
                },
                {
                    "id": "db-h1",
                    "text": "When would you choose a NoSQL store over a relational database?",
                    "difficulty": "hard",
                    "expects": ["schema flexibility", "scaling", "consistency"],
                },
            ],
        },
        {
            "id": "topic-systems",
            "title": "System Design",
            "description": "Scalability, APIs, caching, and distributed systems basics.",
            "weight": 1.4,
            "questions": [
                {
                    "id": "sd-e1",
                    "text": "Explain what an API endpoint is.",
                    "difficulty": "easy",
                    "expects": ["http", "request", "response"],
                },
                {
                    "id": "sd-m1",
                    "text": "Design a URL shortener. What are the key components?",
                    "difficulty": "medium",
                    "expects": ["hash function", "database", "caching", "load balancer"],
                },
                {
                    "id": "sd-h1",
                    "text": "How would you scale a read-heavy web service?",
                    "difficulty": "hard",
                    "expects": ["caching", "read replicas", "load balancing"],
                },
            ],
        },
        {
            "id": "topic-testing",
            "title": "Software Testing",
            "description": "Testing strategies and techniques.",
            "weight": 0.9,
            "questions": [
                {
                    "id": "ts-e1",
                    "text": "Explain the difference between unit and integration tests.",
                    "difficulty": "easy",
                    "expects": ["isolation", "dependencies", "scope"],
                },
                {
                    "id": "ts-m1",
                    "text": "How would you test a function that calls an external API?",
                    "difficulty": "medium",
                    "expects": ["mocking", "stubbing", "side effects"],
                },
            ],
        },
        {
            "id": "topic-algorithms",
            "title": "Algorithms & Data Structures",
            "description": "Core algorithmic techniques.",
            "weight": 1.1,
            "questions": [
                {
                    "id": "al-m1",
                    "text": "Explain the time complexity of a binary search.",
                    "difficulty": "medium",
                    "expects": ["logarithmic", "sorted input"],
                },
                {
                    "id": "al-h1",
                    "text": "Design an algorithm to find the most frequent element in a list.",
                    "difficulty": "hard",
                    "expects": ["hashmap", "counting", "linear time"],
                },
            ],
        },
    ],
}


def _write_json(tmp_path: Path, name: str, payload: object) -> Path:
    """Write ``payload`` as ``name`` inside a temp data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, Path):
        shutil.copy(payload, data_dir / name)
    else:
        (data_dir / name).write_text(json.dumps(payload), encoding="utf-8")
    return data_dir


def _build_planner(
    tmp_path: Path,
    curriculum_payload: object,
    candidate_payload: object,
) -> QuestionPlanner:
    """Wire a loader/analyzer/planner against temp curriculum + candidate files."""
    curriculum_dir = _write_json(tmp_path / "cur", "curriculum.json", curriculum_payload)
    candidate_dir = _write_json(tmp_path / "cand", "candidate.json", candidate_payload)
    return QuestionPlanner(
        curriculum_loader=CurriculumLoader(data_dir=curriculum_dir),
        candidate_analyzer=CandidateAnalyzer(data_dir=candidate_dir),
    )


def _profile_a() -> CandidateProfile:
    """Candidate profile leaning toward System Design (beginner) + strong Python."""
    return CandidateProfile(
        id="candidate-a",
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
        learning_journey=[],
        preferred_languages=["Python", "JavaScript"],
        focus_areas=["Backend API design", "Databases", "Testing"],
        notes="Prefers practical examples over theory; learning SQL depth and system design next.",
    )


def _analysis_a(**overrides: object) -> CandidateAnalysis:
    base = CandidateAnalysis(
        candidate_id="candidate-a",
        profile=_profile_a(),
        completed_topics=["Python for Everybody", "RESTful Blog API", "LeetCode / Codewars"],
        skipped_topics=[],
        attempts={},
        learning_signals=[
            "preferred language: Python",
            "focus area: Databases",
            "learning SQL depth and system design next",
            "has completed project work",
        ],
        strengths=["Python (intermediate)", "Django (intermediate)"],
        areas_for_further_assessment=[
            "SQL (beginner)",
            "Docker (beginner)",
            "System Design (beginner)",
            "SQL depth and system design",
        ],
    )
    return base.model_copy(update=overrides) if overrides else base


def _analysis_b() -> CandidateAnalysis:
    """Candidate profile leaning strongly toward Python, weak elsewhere."""
    return CandidateAnalysis(
        candidate_id="candidate-b",
        profile=CandidateProfile(
            id="candidate-b",
            name="Bea Lin",
            role="Backend Engineer",
            skills=[
                SkillLevel(name="Python", level="advanced"),
                SkillLevel(name="SQL", level="intermediate"),
            ],
            preferred_languages=["Python"],
            focus_areas=["Python internals"],
            notes="Wants to go deeper into Python internals.",
        ),
        completed_topics=["Python for Everybody", "RESTful Blog API"],
        skipped_topics=[],
        attempts={},
        learning_signals=["preferred language: Python"],
        strengths=["Python (advanced)"],
        areas_for_further_assessment=["Advanced Python"],
    )


@pytest.fixture()
def curriculum() -> Curriculum:
    """The synthetic 5-topic curriculum as a validated model."""
    return Curriculum(**CURRICULUM_PLAN)


# --- Plan generation --------------------------------------------------------


class TestPlanGeneration:
    def test_plan_generation_succeeds(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum)
        assert isinstance(plan, InterviewPlan)
        assert plan.candidate_id == "candidate-a"
        assert plan.curriculum_id == curriculum.id

    def test_at_least_8_questions(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum)
        assert plan.total_questions >= MIN_QUESTIONS
        assert len(plan.questions) == 8

    def test_at_least_4_topics_covered(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum)
        assert len(set(plan.topics_covered)) >= MIN_TOPICS
        assert len(set(q.topic_id for q in plan.questions)) >= MIN_TOPICS

    def test_questions_are_grounded_in_curriculum(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum)
        supplied_texts = {q.text for topic in curriculum.topics for q in topic.questions}
        for question in plan.questions:
            assert question.text in supplied_texts
            assert question.curriculum_question_id in {
                q.id for topic in curriculum.topics for q in topic.questions
            }

    def test_create_plan_end_to_end(self, tmp_path: Path) -> None:
        candidate_payload = {
            "id": "candidate-001",
            "name": "Alex Rivera",
            "role": "Backend Engineer",
            "years_of_experience": 2.0,
            "skills": [
                {"name": "Python", "level": "intermediate"},
                {"name": "SQL", "level": "beginner"},
                {"name": "Django", "level": "intermediate"},
                {"name": "Docker", "level": "beginner"},
                {"name": "System Design", "level": "beginner"},
            ],
            "learning_journey": [],
            "preferred_languages": ["Python"],
            "focus_areas": ["Databases"],
            "notes": "learning SQL depth and system design next.",
        }
        planner = _build_planner(tmp_path, CURRICULUM_PLAN, candidate_payload)
        plan = planner.create_plan("candidate-001", "curriculum-plan")
        assert isinstance(plan, InterviewPlan)
        assert plan.total_questions == 8
        assert len(set(plan.topics_covered)) >= MIN_TOPICS

    def test_real_curriculum_builds_complete_plan(self) -> None:
        """The shipped curriculum now meets production minimums (4 topics / 40 questions)."""
        planner = QuestionPlanner(
            curriculum_loader=CurriculumLoader(),
            candidate_analyzer=CandidateAnalyzer(),
        )
        plan = planner.create_plan("candidate-001", "curriculum-001")
        assert isinstance(plan, InterviewPlan)
        assert plan.total_questions == MIN_QUESTIONS
        assert len(set(plan.topics_covered)) >= MIN_TOPICS
        assert plan.is_complete is True


# --- Personalization / skipped topics ---------------------------------------


class TestPersonalization:
    def test_personalization_affects_topic_selection(self, curriculum: Curriculum) -> None:
        plan_a = _plan_for(_analysis_a(), curriculum)
        plan_b = _plan_for(_analysis_b(), curriculum)
        assert plan_a.questions[0].topic_id == "topic-systems"
        assert plan_b.questions[0].topic_id == "topic-python"
        assert plan_a.questions[0].topic_id != plan_b.questions[0].topic_id

    def test_skipped_topics_are_deprioritized(self, curriculum: Curriculum) -> None:
        plan_normal = _plan_for(_analysis_a(), curriculum)
        plan_skipped = _plan_for(_analysis_a(skipped_topics=["System Design"]), curriculum)

        assert plan_normal.questions[0].topic_id == "topic-systems"
        assert plan_skipped.questions[0].topic_id != "topic-systems"
        skipped_ids = {q.topic_id for q in plan_skipped.questions}
        assert "topic-systems" not in skipped_ids


# --- Difficulty / metadata ---------------------------------------------------


class TestDifficultyAndMetadata:
    def test_difficulty_progression(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum)
        assert plan.questions[0].difficulty == "easy"
        assert plan.questions[-1].difficulty == "hard"
        difficulties = {q.difficulty for q in plan.questions}
        assert {"easy", "medium", "hard"} <= difficulties

    def test_no_duplicate_curriculum_questions(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum)
        ids = [q.curriculum_question_id for q in plan.questions]
        assert len(ids) == len(set(ids)) == MIN_QUESTIONS

    def test_follow_up_metadata_present(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum)
        assert all(isinstance(q.follow_up_allowed, bool) for q in plan.questions)
        assert plan.questions[-1].follow_up_allowed is False
        assert all(q.follow_up_allowed for q in plan.questions[:-1])
        assert all(q.question_type for q in plan.questions)
        assert all(q.expects for q in plan.questions)

    def test_sequences_are_contiguous(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum)
        assert [q.sequence for q in plan.questions] == list(range(1, MIN_QUESTIONS + 1))


# --- Errors -----------------------------------------------------------------


class TestErrors:
    def test_insufficient_curriculum_topics_error(self) -> None:
        tiny = Curriculum(
            id="curriculum-tiny",
            title="Tiny",
            topics=[
                Topic(id="t1", title="One", questions=[_q("t1q1")]),
                Topic(id="t2", title="Two", questions=[_q("t2q1")]),
                Topic(id="t3", title="Three", questions=[_q("t3q1")]),
            ],
        )
        with pytest.raises(ValidationError, match="at least 4 usable topics"):
            _plan_for(_analysis_a(), tiny)

    def test_insufficient_questions_error(self) -> None:
        short = Curriculum(
            id="curriculum-short",
            title="Short",
            topics=[
                Topic(id="t1", title="One", questions=[_q("t1q1"), _q("t1q2")]),
                Topic(id="t2", title="Two", questions=[_q("t2q1")]),
                Topic(id="t3", title="Three", questions=[_q("t3q1")]),
                Topic(id="t4", title="Four", questions=[_q("t4q1"), _q("t4q2"), _q("t4q3")]),
            ],
        )
        with pytest.raises(ValidationError, match="at least 8 are required"):
            _plan_for(_analysis_a(), short)


# --- Development mode --------------------------------------------------------


class TestDevelopmentMode:
    def test_partial_curriculum_plans_instead_of_raising(self) -> None:
        small = Curriculum(
            id="curriculum-small",
            title="Small",
            topics=[
                Topic(id="t1", title="One", questions=[_q("t1q1"), _q("t1q2")]),
                Topic(id="t2", title="Two", questions=[_q("t2q1")]),
                Topic(id="t3", title="Three", questions=[_q("t3q1"), _q("t3q2")]),
            ],
        )
        plan = _plan_for(_analysis_a(), small, development_mode=True)
        assert isinstance(plan, InterviewPlan)
        assert plan.total_questions == 5
        assert len(plan.questions) == 5
        assert plan.is_complete is False
        assert plan.completeness_metadata["missing_topics"] == 1
        assert plan.completeness_metadata["missing_questions"] == 3
        assert "incomplete" in plan.completeness_metadata["reason"]

    def test_full_curriculum_selects_every_question(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum, development_mode=True)
        assert plan.total_questions == 13
        assert plan.is_complete is True
        assert plan.completeness_metadata["missing_topics"] == 0
        assert plan.completeness_metadata["missing_questions"] == 0

    def test_dev_mode_questions_are_grounded_and_unique(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_analysis_a(), curriculum, development_mode=True)
        supplied_ids = {q.id for topic in curriculum.topics for q in topic.questions}
        planned_ids = {q.curriculum_question_id for q in plan.questions}
        assert planned_ids == supplied_ids
        assert len(planned_ids) == plan.total_questions

    def test_tiny_curriculum_single_question(self) -> None:
        tiny = Curriculum(
            id="curriculum-tiny-dev",
            title="Tiny",
            topics=[Topic(id="t1", title="One", questions=[_q("t1q1")])],
        )
        plan = _plan_for(_analysis_a(), tiny, development_mode=True)
        assert plan.total_questions == 1
        assert plan.questions[0].sequence == 1
        assert plan.questions[0].follow_up_allowed is False
        assert plan.is_complete is False
        assert plan.completeness_metadata["missing_topics"] == 3
        assert plan.completeness_metadata["missing_questions"] == 7

    def test_empty_curriculum_dev_mode(self) -> None:
        empty = Curriculum(id="curriculum-empty", title="Empty", topics=[])
        plan = _plan_for(_analysis_a(), empty, development_mode=True)
        assert plan.total_questions == 0
        assert plan.questions == []
        assert plan.topics_covered == []
        assert plan.is_complete is False
        assert plan.completeness_metadata["missing_topics"] == 4
        assert plan.completeness_metadata["missing_questions"] == 8

    def test_constructor_development_mode_applies_to_create_plan(self) -> None:
        planner = QuestionPlanner(
            curriculum_loader=CurriculumLoader(),
            candidate_analyzer=CandidateAnalyzer(),
            development_mode=True,
        )
        plan = planner.create_plan("candidate-001", "curriculum-001")
        assert plan.total_questions == 40
        assert plan.is_complete is True

    def test_app_di_plans_real_curriculum_in_development_env(self) -> None:
        """The app's DI wiring (dev env) must plan the shipped curriculum.

        Phase 6 regression guard: with the default ``app_env == development``
        the dependency graph builds the planner in development mode, so
        ``POST /api/interview`` can actually start. The shipped curriculum
        (4 topics / 40 questions) exceeds the production minimums, so even in
        production mode a complete plan can be built.
        """
        settings = Settings()
        assert settings.app_env == "development"
        planner = QuestionPlanner(
            curriculum_loader=CurriculumLoader(),
            candidate_analyzer=CandidateAnalyzer(),
            development_mode=settings.app_env != "production",
        )
        plan = planner.create_plan("candidate-001", "curriculum-001")
        assert plan.total_questions == 40
        assert plan.is_complete is True

    def test_per_call_override_beats_constructor_default(self, curriculum: Curriculum) -> None:
        planner = QuestionPlanner(
            curriculum_loader=CurriculumLoader(data_dir=Path()),
            candidate_analyzer=CandidateAnalyzer(data_dir=Path()),
        )
        plan = planner.plan_for(_analysis_a(), curriculum, development_mode=True)
        assert plan.total_questions == 13
        assert plan.is_complete is True

    def test_production_mode_still_rejects_partial_curriculum(self) -> None:
        small = Curriculum(
            id="curriculum-small",
            title="Small",
            topics=[
                Topic(id="t1", title="One", questions=[_q("t1q1")]),
                Topic(id="t2", title="Two", questions=[_q("t2q1")]),
                Topic(id="t3", title="Three", questions=[_q("t3q1")]),
            ],
        )
        with pytest.raises(ValidationError, match="at least 4 usable topics"):
            _plan_for(_analysis_a(), small)


# --- Determinism -------------------------------------------------------------


class TestDeterminism:
    def test_deterministic_output_for_identical_input(
        self, tmp_path: Path
    ) -> None:
        candidate_payload = {
            "id": "candidate-001",
            "name": "Alex Rivera",
            "role": "Backend Engineer",
            "skills": [
                {"name": "Python", "level": "intermediate"},
                {"name": "System Design", "level": "beginner"},
            ],
            "preferred_languages": ["Python"],
            "focus_areas": ["Databases"],
            "notes": "learning SQL depth and system design next.",
        }
        planner = _build_planner(tmp_path, CURRICULUM_PLAN, candidate_payload)
        first = planner.create_plan("candidate-001", "curriculum-plan")
        second = planner.create_plan("candidate-001", "curriculum-plan")
        assert first == second

    def test_plan_for_is_deterministic(self, curriculum: Curriculum) -> None:
        analysis = _analysis_a()
        assert _plan_for(analysis, curriculum) == _plan_for(analysis, curriculum)


# --- Small helpers ------------------------------------------------------------


def _q(question_id: str, difficulty: str = "medium") -> QuestionTemplate:
    return QuestionTemplate(id=question_id, text=f"Question {question_id}", difficulty=difficulty)


def _plan_for(
    analysis: CandidateAnalysis,
    curriculum: Curriculum,
    *,
    development_mode: bool = False,
) -> InterviewPlan:
    planner = QuestionPlanner(
        curriculum_loader=CurriculumLoader(data_dir=Path()),
        candidate_analyzer=CandidateAnalyzer(data_dir=Path()),
        development_mode=development_mode,
    )
    return planner.plan_for(analysis, curriculum)
