"""Custom-profile difficulty tuning + adaptive per-turn decisions.

Covers three new capabilities end to end:

  1. QuestionPlanner difficulty bias for custom profiles (id prefix ``custom-``):
     junior leans easy, senior leans hard, mid/non-custom stay balanced.
  2. AdaptiveDecider: the per-turn follow-up / next / complete decision, with a
     Gemini path (fully mocked) and a deterministic fallback.
  3. InterviewEngine integration: the decider owns the turn decision, the intro
     advertises the difficulty tuning, and every primary decision is logged.

The synthetic 5-topic curriculum (14 questions across easy/medium/hard) matches
the engine's default curriculum id so full interviews are deterministic.
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
from app.models.candidate import CandidateAnalysis, CandidateProfile, SkillLevel
from app.models.curriculum import Curriculum, InterviewPlan
from app.models.session import InterviewState
from app.services.adaptive_decider import (
    ACTION_COMPLETE,
    ACTION_FOLLOW_UP,
    ACTION_NEXT,
    AdaptiveDecider,
)
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator
from app.services.follow_up_advisor import AI_SOURCE, DETERMINISTIC_SOURCE, FollowUpAdvisor
from app.services.gemini_service import GeminiService
from app.services.interview_engine import InterviewEngine
from app.services.memory_engine import MemoryEngine
from app.services.prompt_builder import DECISION_SCHEMA, PromptBuilder
from app.services.question_planner import MIN_TOPICS, QuestionPlanner
from app.services.session_manager import SessionManager
from app.utils.config import Settings
from app.utils.errors import LLMError

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"

#: Synthetic 5-topic curriculum with 14 grounded questions across all tiers.
SYNTHETIC_CURRICULUM = {
    "id": "curriculum-001",
    "title": "Synthetic Interview Curriculum",
    "description": "Five topics with varied-difficulty questions for custom-profile tests.",
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


# --- Planner helpers ----------------------------------------------------------


def _custom_analysis(level: str, *, skills: list[SkillLevel] | None = None) -> CandidateAnalysis:
    """A user-created (``custom-``) profile at the given experience level."""
    return CandidateAnalysis(
        candidate_id=f"custom-{level}-user",
        profile=CandidateProfile(
            id=f"custom-{level}-user",
            name="Sam Lee",
            role="Backend Engineer",
            experience_level=level,
            skills=skills or [SkillLevel(name="Python", level="intermediate")],
        ),
        completed_topics=[],
        skipped_topics=[],
        attempts={},
        learning_signals=[],
        strengths=[],
        areas_for_further_assessment=[],
    )


@pytest.fixture()
def curriculum() -> Curriculum:
    return Curriculum(**SYNTHETIC_CURRICULUM)


def _plan_for(analysis: CandidateAnalysis, curriculum: Curriculum) -> InterviewPlan:
    planner = QuestionPlanner(
        curriculum_loader=CurriculumLoader(data_dir=Path()),
        candidate_analyzer=CandidateAnalyzer(data_dir=Path()),
    )
    return planner.plan_for(analysis, curriculum)


def _difficulty_counts(plan: InterviewPlan) -> dict[str, int]:
    counts: dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    for question in plan.questions:
        counts[question.difficulty] = counts.get(question.difficulty, 0) + 1
    return counts


# --- Planner: custom-profile difficulty tuning --------------------------------


class TestDifficultyTuning:
    def test_custom_junior_bias_is_easy(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_custom_analysis("junior"), curriculum)
        assert plan.difficulty_bias == "easy"
        counts = _difficulty_counts(plan)
        assert counts["easy"] >= 1
        assert plan.questions[0].difficulty == "easy"

    def test_custom_senior_bias_is_hard(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_custom_analysis("senior"), curriculum)
        assert plan.difficulty_bias == "hard"
        counts = _difficulty_counts(plan)
        assert counts["hard"] >= 1
        assert plan.questions[0].difficulty == "hard"

    def test_custom_mid_stays_balanced(self, curriculum: Curriculum) -> None:
        plan = _plan_for(_custom_analysis("mid"), curriculum)
        assert plan.difficulty_bias is None

    def test_unknown_custom_level_stays_balanced(self, curriculum: Curriculum) -> None:
        analysis = _custom_analysis("principal")
        plan = _plan_for(analysis, curriculum)
        assert plan.difficulty_bias is None

    def test_non_custom_profile_ignores_experience_level(self, curriculum: Curriculum) -> None:
        profile = CandidateProfile(
            id="candidate-001",
            name="Alex Rivera",
            role="Backend Engineer",
            experience_level="senior",
            skills=[SkillLevel(name="Python", level="intermediate")],
        )
        plan = _plan_for(
            CandidateAnalysis(
                candidate_id="candidate-001",
                profile=profile,
                completed_topics=[],
                skipped_topics=[],
                attempts={},
                learning_signals=[],
                strengths=[],
                areas_for_further_assessment=[],
            ),
            curriculum,
        )
        assert plan.difficulty_bias is None

    def test_senior_plan_has_more_hard_than_junior(self, curriculum: Curriculum) -> None:
        senior = _difficulty_counts(_plan_for(_custom_analysis("senior"), curriculum))
        junior = _difficulty_counts(_plan_for(_custom_analysis("junior"), curriculum))
        assert senior["hard"] > junior["hard"]
        assert junior["easy"] > senior["easy"]

    def test_custom_plans_meet_production_minimums(self, curriculum: Curriculum) -> None:
        for level in ("junior", "mid", "senior"):
            plan = _plan_for(_custom_analysis(level), curriculum)
            assert plan.total_questions == 8
            assert len(set(plan.topics_covered)) >= MIN_TOPICS
            assert plan.is_complete is True


# --- AdaptiveDecider ----------------------------------------------------------


def _mock_gemini(payload: dict | None = None, error: Exception | None = None) -> mock.MagicMock:
    gemini = mock.MagicMock()
    gemini.enabled = True
    if error is not None:
        gemini.generate_json.side_effect = error
    else:
        gemini.generate_json.return_value = payload
    return gemini


def _disabled_gemini() -> GeminiService:
    return GeminiService(settings=Settings(gemini_enabled=False))


def _decider(gemini, *, prompt_builder: PromptBuilder | None = None) -> AdaptiveDecider:
    builder = prompt_builder or PromptBuilder()
    return AdaptiveDecider(
        prompt_builder=builder,
        gemini_service=gemini,
        follow_up_advisor=FollowUpAdvisor(prompt_builder=builder, gemini_service=gemini),
    )


def _kwargs(**overrides: object) -> dict:
    base = dict(
        session_id="sess-decide",
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
        remaining_questions=3,
        difficulty_bias=None,
    )
    base.update(overrides)
    return base


def _full_eval(question: dict) -> dict:
    return {"score": 10.0, "missing": [], "covered": list(question["expects"])}


class TestAdaptiveDeciderDeterministic:
    def test_missing_concept_triggers_follow_up(self) -> None:
        decision = _decider(_disabled_gemini()).decide(**_kwargs())
        assert decision.action == ACTION_FOLLOW_UP
        assert decision.source == DETERMINISTIC_SOURCE
        assert decision.target_concept in ("immutable", "mutable")
        assert decision.target_concept in decision.question

    def test_all_concepts_covered_moves_to_next(self) -> None:
        kwargs = _kwargs()
        kwargs["evaluation"] = _full_eval(kwargs["question"])
        decision = _decider(_disabled_gemini()).decide(**kwargs)
        assert decision.action == ACTION_NEXT
        assert decision.source == DETERMINISTIC_SOURCE

    def test_no_remaining_questions_completes(self) -> None:
        decision = _decider(_disabled_gemini()).decide(**_kwargs(remaining_questions=0))
        assert decision.action == ACTION_COMPLETE
        assert decision.question == ""

    def test_follow_up_disallowed_advances(self) -> None:
        kwargs = _kwargs()
        kwargs["question"] = {**kwargs["question"], "follow_up_allowed": False}
        decision = _decider(_disabled_gemini()).decide(**kwargs)
        assert decision.action == ACTION_NEXT


class TestAdaptiveDeciderAI:
    def test_ai_requests_follow_up(self) -> None:
        payload = {
            "action": "follow_up",
            "reason": "probe depth",
            "question": "Can you elaborate on immutability?",
            "target_concept": "immutable",
        }
        decision = _decider(_mock_gemini(payload)).decide(**_kwargs())
        assert decision.action == ACTION_FOLLOW_UP
        assert decision.source == AI_SOURCE
        assert decision.question == payload["question"]
        assert decision.target_concept == "immutable"

    def test_ai_requests_next_question(self) -> None:
        decision = _decider(
            _mock_gemini({"action": "next_question", "reason": "clear", "question": "", "target_concept": ""})
        ).decide(**_kwargs())
        assert decision.action == ACTION_NEXT
        assert decision.source == AI_SOURCE

    def test_ai_requests_complete(self) -> None:
        decision = _decider(
            _mock_gemini({"action": "complete", "reason": "done", "question": "", "target_concept": ""})
        ).decide(**_kwargs())
        assert decision.action == ACTION_COMPLETE
        assert decision.source == AI_SOURCE

    def test_ai_follow_up_is_grounded_in_expects(self) -> None:
        decision = _decider(
            _mock_gemini(
                {"action": "follow_up", "reason": "r", "question": "q?", "target_concept": "IMMUTABLE"}
            )
        ).decide(**_kwargs())
        assert decision.action == ACTION_FOLLOW_UP
        assert decision.target_concept == "immutable"

    def test_unknown_action_falls_back(self) -> None:
        decision = _decider(
            _mock_gemini({"action": "skip", "reason": "r", "question": "", "target_concept": ""})
        ).decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE
        assert decision.action == ACTION_FOLLOW_UP

    def test_unknown_target_concept_falls_back(self) -> None:
        decision = _decider(
            _mock_gemini(
                {"action": "follow_up", "reason": "r", "question": "q?", "target_concept": "quantum"}
            )
        ).decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE
        assert decision.target_concept in ("immutable", "mutable")

    def test_llm_error_falls_back(self) -> None:
        decision = _decider(_mock_gemini(error=LLMError("boom"))).decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE
        assert decision.action == ACTION_FOLLOW_UP

    def test_disabled_gemini_never_called(self) -> None:
        gemini = _mock_gemini({"action": "next_question", "reason": "r", "question": "", "target_concept": ""})
        gemini.enabled = False
        decision = _decider(gemini).decide(**_kwargs())
        assert decision.source == DETERMINISTIC_SOURCE
        gemini.generate_json.assert_not_called()

    def test_schema_is_applied_to_generate_json(self) -> None:
        gemini = _mock_gemini({"action": "next_question", "reason": "r", "question": "", "target_concept": ""})
        _decider(gemini).decide(**_kwargs())
        args, _ = gemini.generate_json.call_args
        assert args[0].startswith("You are a senior technical interviewer")
        assert args[1] == DECISION_SCHEMA

    def test_prompt_includes_plan_state(self) -> None:
        builder = PromptBuilder()
        prompt = builder.build_decision_prompt(
            session_id="sess-prompt",
            topic=_kwargs()["topic"],
            question=_kwargs()["question"],
            answer="I'm not sure.",
            evaluation=_kwargs()["evaluation"],
            conversation_context=[],
            remaining_questions=2,
            difficulty_bias="hard",
        )
        assert "remaining primary questions: 2" in prompt
        assert "difficulty_bias: hard" in prompt
        assert "follow_up" in prompt


# --- InterviewEngine integration ----------------------------------------------


def _candidate(level: str = "mid") -> CandidateProfile:
    return CandidateProfile(
        id=f"custom-{level}-user",
        name="Sam Lee",
        role="Backend Engineer",
        experience_level=level,
        skills=[SkillLevel(name="Python", level="intermediate")],
    )


def _build_stack(tmp_path: Path, decider: AdaptiveDecider | None = None) -> SimpleNamespace:
    """Wire a full engine stack with an optional AdaptiveDecider."""
    data_dir = _write_curriculum(tmp_path, SYNTHETIC_CURRICULUM)
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
        adaptive_decider=decider,
    )
    return SimpleNamespace(
        engine=engine,
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


class TestEngineCustomProfiles:
    def test_senior_start_builds_biased_plan_and_intro(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path)
        resp = stack.engine.start("sess-senior", _candidate("senior"))
        context = _context(stack, "sess-senior")
        assert context["plan"]["difficulty_bias"] == "hard"
        assert context["difficulty_bias"] == "hard"
        assert "senior-level" in resp.reply
        assert "You will be asked 8 questions" in resp.reply

    def test_junior_start_builds_biased_plan_and_intro(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path)
        resp = stack.engine.start("sess-junior", _candidate("junior"))
        context = _context(stack, "sess-junior")
        assert context["plan"]["difficulty_bias"] == "easy"
        assert "junior-friendly" in resp.reply

    def test_mid_start_stays_balanced_intro(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path)
        resp = stack.engine.start("sess-mid", _candidate("mid"))
        context = _context(stack, "sess-mid")
        assert context["plan"]["difficulty_bias"] is None
        assert "tuned the questions" not in resp.reply

    def test_decider_follow_up_then_advance(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(
            {"action": "follow_up", "reason": "probe", "question": "Tell me more about immutability.", "target_concept": "immutable"}
        )
        decider = _decider(gemini)
        stack = _build_stack(tmp_path, decider)
        stack.engine.start("sess-ai", _candidate())
        questions = _questions(stack, "sess-ai")

        resp = stack.engine.handle_answer("sess-ai", _weak_answer(questions[0]))
        assert resp.done is False
        assert resp.reply == "Tell me more about immutability."
        context = _context(stack, "sess-ai")
        assert InterviewState(stack.session_manager.get_session("sess-ai").state) == InterviewState.FOLLOW_UP
        assert context["phase"] == "follow_up"
        assert context["pending_follow_up"] == "immutable"
        assert context["follow_ups"][0]["source"] == AI_SOURCE
        assert context["decisions"][0]["action"] == ACTION_FOLLOW_UP

        resp = stack.engine.handle_answer("sess-ai", _full_answer(questions[0]))
        assert resp.reply == questions[1]["text"]
        assert _context(stack, "sess-ai")["phase"] == "question"

    def test_decider_next_question_skips_follow_up(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(
            {"action": "next_question", "reason": "answer sufficient", "question": "", "target_concept": ""}
        )
        stack = _build_stack(tmp_path, _decider(gemini))
        stack.engine.start("sess-next", _candidate())
        questions = _questions(stack, "sess-next")
        resp = stack.engine.handle_answer("sess-next", _weak_answer(questions[0]))
        assert resp.reply == questions[1]["text"]
        context = _context(stack, "sess-next")
        assert context["follow_up_count"] == 0
        assert context["decisions"][0]["action"] == ACTION_NEXT

    def test_engine_coerces_premature_ai_complete(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(
            {"action": "complete", "reason": "early", "question": "", "target_concept": ""}
        )
        stack = _build_stack(tmp_path, _decider(gemini))
        stack.engine.start("sess-early", _candidate())
        questions = _questions(stack, "sess-early")
        resp = stack.engine.handle_answer("sess-early", _full_answer(questions[0]))
        assert resp.done is False
        assert resp.reply == questions[1]["text"]
        context = _context(stack, "sess-early")
        assert context["decisions"][0]["action"] == ACTION_NEXT
        assert "premature" in context["decisions"][0]["reason"]

    def test_full_interview_with_decider_logs_decisions(self, tmp_path: Path) -> None:
        gemini = _mock_gemini(
            {"action": "next_question", "reason": "proceed", "question": "", "target_concept": ""}
        )
        stack = _build_stack(tmp_path, _decider(gemini))
        stack.engine.start("sess-full", _candidate())
        resp = stack.engine.handle_answer("sess-full", _weak_answer(_current(stack, "sess-full")))
        while not resp.done:
            resp = stack.engine.handle_answer("sess-full", _weak_answer(_current(stack, "sess-full")))

        assert resp.done is True
        assert resp.feedback is not None
        context = _context(stack, "sess-full")
        assert context["primary_question_count"] == 8
        decisions = context["decisions"]
        assert len(decisions) == 8
        assert all(entry["action"] == ACTION_NEXT for entry in decisions[:-1])
        assert decisions[-1]["action"] == ACTION_COMPLETE
        assert InterviewState(stack.session_manager.get_session("sess-full").state) == InterviewState.COMPLETED

    def test_deterministic_decider_interview_completes(self, tmp_path: Path) -> None:
        """Weak answers + a decider on disabled Gemini = deterministic follow-ups."""
        stack = _build_stack(tmp_path, _decider(_disabled_gemini()))
        stack.engine.start("sess-det", _candidate())
        resp = stack.engine.handle_answer("sess-det", _weak_answer(_current(stack, "sess-det")))
        while not resp.done:
            resp = stack.engine.handle_answer("sess-det", _weak_answer(_current(stack, "sess-det")))

        context = _context(stack, "sess-det")
        assert context["primary_question_count"] == 8
        assert context["follow_up_count"] >= 1
        assert all(entry["source"] == DETERMINISTIC_SOURCE for entry in context["decisions"])
        assert context["follow_ups"][0]["source"] == DETERMINISTIC_SOURCE

    def test_real_curriculum_custom_senior_plan(self, tmp_path: Path) -> None:
        stack = _build_stack(tmp_path, REAL_DATA_DIR / "curriculum.json")
        resp = stack.engine.start("sess-real", _candidate("senior"))
        assert resp.done is False
        context = _context(stack, "sess-real")
        assert context["plan"]["difficulty_bias"] == "hard"
        assert len(context["plan"]["questions"]) == 8
