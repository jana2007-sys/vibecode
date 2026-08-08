"""Interview orchestration.

Top-level coordinator for the conversation loop: moves the session through the
state machine, asks questions, collects answers, evaluates them, and hands the
results to the feedback service. Everything here is deterministic — no LLM.

Conversation flow per the interactive contract:

  START -> INTRODUCTION -> QUESTION -> [FOLLOW_UP] -> NEXT_TOPIC -> ... -> SUMMARY -> COMPLETED

- ``start`` analyzes the candidate, builds the plan, stores it in the session
  context, and asks the first primary question.
- ``handle_answer`` records and evaluates each answer. A primary answer that
  misses concepts (and allows follow-up) triggers exactly one grounded
  follow-up; otherwise the engine advances to the next primary. After the last
  primary the session completes and the FeedbackGenerator produces the report.

Collaborators: SessionManager, QuestionPlanner, EvaluationEngine, MemoryEngine,
CurriculumLoader, CandidateAnalyzer, FeedbackGenerator, MessageRepository.
"""

from __future__ import annotations

from collections import Counter

from app.database.repositories.message_repository import MessageRepository
from app.models.candidate import CandidateProfile
from app.models.common import new_uuid, utc_now
from app.models.interview import InterviewFeedback, InterviewTurnResponse
from app.models.message import MessageRole
from app.models.session import InterviewState, SessionCreate
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator
from app.services.memory_engine import MemoryEngine
from app.services.question_planner import QuestionPlanner
from app.services.session_manager import SessionManager
from app.utils.errors import NotFoundError, ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Curriculum used when the interactive engine is the entry point.
DEFAULT_CURRICULUM_ID = "curriculum-001"

#: How many "next step" suggestions to include in the final feedback.
MAX_NEXT_STEPS = 3


class InterviewEngine:
    """Runs one adaptive interview conversation."""

    def __init__(
        self,
        session_manager: SessionManager,
        question_planner: QuestionPlanner,
        evaluation_engine: EvaluationEngine,
        memory_engine: MemoryEngine,
        *,
        curriculum_loader: CurriculumLoader,
        candidate_analyzer: CandidateAnalyzer,
        feedback_generator: FeedbackGenerator,
        message_repository: MessageRepository,
        default_curriculum_id: str = DEFAULT_CURRICULUM_ID,
    ) -> None:
        self._sessions = session_manager
        self._planner = question_planner
        self._evaluator = evaluation_engine
        self._memory = memory_engine
        self._curriculum = curriculum_loader
        self._analyzer = candidate_analyzer
        self._feedback = feedback_generator
        self._messages = message_repository
        self._default_curriculum_id = default_curriculum_id

    # --- Entry points --------------------------------------------------------

    def start(self, session_id: str, candidate: CandidateProfile) -> InterviewTurnResponse:
        """Begin an interview: create the session, plan, and ask Q1."""
        try:
            existing = self._sessions.get_session(session_id)
        except NotFoundError:
            existing = None
        if existing is not None and InterviewState(existing.state) != InterviewState.START:
            raise ValidationError(f"Session {session_id} has already started")

        curriculum = self._curriculum.load_curriculum(self._default_curriculum_id)
        analysis = self._analyzer.analyze_profile(candidate)
        plan = self._planner.plan_for(analysis, curriculum)

        if existing is None:
            self._sessions.create_session(
                SessionCreate(candidate_id=analysis.candidate_id, curriculum_id=curriculum.id),
                session_id=session_id,
            )

        first = plan.questions[0]
        context = {
            "candidate_id": analysis.candidate_id,
            "curriculum_id": curriculum.id,
            "plan": plan.model_dump(mode="json"),
            "analysis": analysis.model_dump(mode="json"),
            "topics": [topic.model_dump(mode="json") for topic in curriculum.topics],
            "primary_index": 0,
            "phase": "question",
            "current": first.model_dump(mode="json"),
            "pending_follow_up": None,
            "primary_question_count": 0,
            "follow_up_count": 0,
            "primary_answered": 0,
            "topics_covered": [first.topic_id],
            "asked_questions": [first.model_dump(mode="json")],
            "answers": [],
            "evaluations": [],
        }
        self._sessions.update_context(session_id, context)

        # START -> INTRODUCTION -> QUESTION
        self._sessions.advance(session_id, InterviewState.INTRODUCTION)
        self._sessions.advance(session_id, InterviewState.QUESTION)

        reply = self._build_intro(candidate, plan) + "\n\n" + first.text
        self._persist_interviewer(session_id, reply, question=first.model_dump(mode="json"), kind="question")
        logger.info("Interview %s started with plan %s", session_id, plan.curriculum_id)
        return InterviewTurnResponse(reply=reply, done=False)

    def handle_answer(self, session_id: str, answer: str) -> InterviewTurnResponse:
        """Process a candidate answer and return the next interviewer turn.

        When the answer completes the final primary the interview transitions to
        SUMMARY then COMPLETED and the response carries the generated feedback.
        """
        session = self._sessions.get_session(session_id)
        if InterviewState(session.state) == InterviewState.COMPLETED:
            raise ValidationError(f"Session {session_id} is already completed")

        context = dict(session.context)
        current = context.get("current")
        if current is None:
            raise ValidationError(f"Session {session_id} has no active question")

        phase = context.get("phase", "question")
        self._persist_candidate(session_id, answer, question=current, kind="answer")

        _, missing = self._evaluator.concept_coverage(answer, current["expects"])
        score = self._evaluator.evaluate_answer(
            session_id,
            current["topic_id"],
            current["curriculum_question_id"],
            answer,
            expects=current["expects"],
        )
        context["evaluations"].append(
            {
                "question_id": current["curriculum_question_id"],
                "topic_id": current["topic_id"],
                "kind": "primary" if phase == "question" else "follow_up",
                "score": score,
                "missing": list(missing),
            }
        )
        context["answers"].append(
            {
                "question_id": current["curriculum_question_id"],
                "topic_id": current["topic_id"],
                "answer": answer,
                "score": score,
            }
        )

        if phase == "question":
            context["primary_question_count"] += 1
            context["primary_answered"] += 1

            if missing and current.get("follow_up_allowed", False):
                context["phase"] = "follow_up"
                context["pending_follow_up"] = missing[0]
                self._sessions.advance(session_id, InterviewState.FOLLOW_UP)
                self._sessions.update_context(session_id, context)
                follow_up_text = self._build_follow_up(current, missing[0])
                self._persist_interviewer(
                    session_id, follow_up_text, question=current, kind="follow_up"
                )
                return InterviewTurnResponse(reply=follow_up_text, done=False)
        else:
            context["follow_up_count"] += 1
            context["primary_answered"] += 1
            context["pending_follow_up"] = None
            context["phase"] = "question"

        return self._advance_after_primary(session_id, context)

    # --- Progression ---------------------------------------------------------

    def _advance_after_primary(self, session_id: str, context: dict) -> InterviewTurnResponse:
        """Move past the answered primary: next question or completion."""
        plan = context["plan"]
        next_index = context["primary_index"] + 1

        if next_index < len(plan["questions"]):
            # QUESTION -> NEXT_TOPIC -> QUESTION (legal from FOLLOW_UP too).
            self._sessions.advance(session_id, InterviewState.NEXT_TOPIC)
            self._sessions.advance(session_id, InterviewState.QUESTION)

            next_question = plan["questions"][next_index]
            context["primary_index"] = next_index
            context["current"] = next_question
            context["phase"] = "question"
            if next_question["topic_id"] not in context["topics_covered"]:
                context["topics_covered"].append(next_question["topic_id"])
            context["asked_questions"].append(next_question)
            self._sessions.update_context(
                session_id,
                context,
                topic_index=self._topic_index_of(context["topics"], next_question["topic_id"]),
            )
            self._persist_interviewer(session_id, next_question["text"], question=next_question, kind="question")
            return InterviewTurnResponse(reply=next_question["text"], done=False)

        # Final answer: QUESTION/FOLLOW_UP -> SUMMARY -> COMPLETED.
        self._sessions.advance(session_id, InterviewState.SUMMARY)
        self._sessions.advance(session_id, InterviewState.COMPLETED)
        self._sessions.update_context(session_id, context)

        report = self._feedback.generate_report(session_id)
        closing = self._build_closing(report)
        self._persist_interviewer(session_id, closing, question=None, kind="closing")
        logger.info("Interview %s completed (overall %.2f)", session_id, report.overall_score)
        return InterviewTurnResponse(
            reply=closing,
            done=True,
            feedback=self._to_feedback(context, report),
        )

    # --- Messages ------------------------------------------------------------

    def _persist_interviewer(
        self,
        session_id: str,
        text: str,
        *,
        question: dict | None,
        kind: str,
    ) -> None:
        metadata = {"kind": kind}
        if question:
            metadata["question_id"] = question["curriculum_question_id"]
            metadata["topic_id"] = question["topic_id"]
        self._messages.create(
            message_id=new_uuid(),
            session_id=session_id,
            role=MessageRole.INTERVIEWER.value,
            content=text,
            metadata=metadata,
            created_at=utc_now(),
        )
        self._memory.record_turn(session_id, MessageRole.INTERVIEWER.value, text)

    def _persist_candidate(
        self,
        session_id: str,
        text: str,
        *,
        question: dict,
        kind: str,
    ) -> None:
        metadata = {"kind": kind, "question_id": question["curriculum_question_id"], "topic_id": question["topic_id"]}
        self._messages.create(
            message_id=new_uuid(),
            session_id=session_id,
            role=MessageRole.CANDIDATE.value,
            content=text,
            metadata=metadata,
            created_at=utc_now(),
        )
        self._memory.record_turn(session_id, MessageRole.CANDIDATE.value, text)

    # --- Text builders -------------------------------------------------------

    @staticmethod
    def _build_intro(candidate: CandidateProfile, plan) -> str:
        return (
            f"Welcome, {candidate.name}! This is your InterVue AI technical interview. "
            f"You will be asked {plan.total_questions} questions across "
            f"{len(plan.topics_covered)} topics. Let's begin."
        )

    @staticmethod
    def _build_follow_up(question: dict, concept: str) -> str:
        return (
            f"You didn't mention '{concept}'. Could you explain how "
            f"'{concept}' relates to your answer?"
        )

    @staticmethod
    def _build_closing(report) -> str:
        return (
            f"Thank you, your interview is complete! "
            f"Overall score: {report.overall_score:.1f}/10. {report.summary}"
        )

    # --- Feedback mapping ----------------------------------------------------

    def _to_feedback(self, context: dict, report) -> InterviewFeedback:
        """Map the persisted report plus context into the response feedback."""
        missing_counter: Counter[str] = Counter()
        for evaluation in context.get("evaluations", []):
            missing_counter.update(evaluation.get("missing", []))

        next_steps: list[str] = []
        for area in context.get("analysis", {}).get("areas_for_further_assessment", []):
            if area not in next_steps:
                next_steps.append(area)
        for concept, _ in missing_counter.most_common(MAX_NEXT_STEPS):
            if concept not in next_steps:
                next_steps.append(concept)

        return InterviewFeedback(
            summary=report.summary,
            strengths=list(report.strengths),
            gaps=list(report.improvements),
            next=next_steps,
        )

    # --- Helpers -------------------------------------------------------------

    @staticmethod
    def _topic_index_of(topics: list[dict], topic_id: str) -> int:
        """Return the curriculum index of a topic id (0 when unknown)."""
        for index, topic in enumerate(topics):
            if topic.get("id") == topic_id:
                return index
        return 0
