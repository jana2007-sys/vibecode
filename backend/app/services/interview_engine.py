"""Interview orchestration.

Top-level coordinator for the conversation loop: moves the session through the
state machine, asks questions, collects answers, evaluates them, and hands the
results to the feedback service. Everything here is deterministic — no LLM.

Conversation flow per the interactive contract:

  START -> INTRODUCTION -> QUESTION -> [FOLLOW_UP] -> NEXT_TOPIC -> ... -> SUMMARY -> COMPLETED

- ``start`` analyzes the candidate, builds the plan, stores it in the session
  context, and asks the first primary question.
- ``handle_answer`` records and evaluates each answer. A primary answer may
  trigger exactly one follow-up, move to the next primary, or end the interview.
  When an AdaptiveDecider is wired it owns that decision (Gemini with a
  deterministic fallback); otherwise the classic concept-coverage heuristic
  applies. After the follow-up, or when none is warranted, the engine advances
  to the next primary. After the last primary the session completes and the
  FeedbackGenerator produces the report.

Collaborators: SessionManager, QuestionPlanner, EvaluationEngine, MemoryEngine,
CurriculumLoader, CandidateAnalyzer, FeedbackGenerator, MessageRepository,
AdaptiveDecider.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace as replace_decision

from app.database.repositories.message_repository import MessageRepository
from app.models.candidate import CandidateProfile
from app.models.common import new_uuid, utc_now
from app.models.interview import InterviewFeedback, InterviewTurnResponse
from app.models.message import MessageRole
from app.models.session import InterviewState, SessionCreate
from app.services.adaptive_decider import (
    ACTION_COMPLETE,
    ACTION_FOLLOW_UP,
    ACTION_NEXT,
    AdaptiveDecider,
    InterviewDecision,
)
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator, NEXT_STEP_PREFIX
from app.services.follow_up_advisor import FollowUpAdvisor
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
        follow_up_advisor: FollowUpAdvisor | None = None,
        adaptive_decider: AdaptiveDecider | None = None,
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
        self._follow_up_advisor = follow_up_advisor
        self._adaptive_decider = adaptive_decider

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
            "follow_ups": [],
            "decisions": [],
            "difficulty_bias": plan.difficulty_bias,
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

        Flow: deterministic evaluation -> (AI) turn decision (follow-up, next
        primary, or completion) -> at most one follow-up. When the answer
        completes the final primary the interview transitions to SUMMARY then
        COMPLETED and the response carries the generated feedback.
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

        covered, missing = self._evaluator.concept_coverage(answer, current["expects"])
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
                "covered": list(covered),
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

            decision = self._decide_next(
                session_id,
                context,
                current,
                answer,
                score,
                list(missing),
                list(covered),
            )
            context["decisions"].append(
                {
                    "question_id": current["curriculum_question_id"],
                    "topic_id": current["topic_id"],
                    **decision,
                }
            )
            if decision["action"] == ACTION_FOLLOW_UP:
                context["phase"] = "follow_up"
                context["pending_follow_up"] = decision["target_concept"]
                context["follow_ups"].append(
                    {
                        "question": decision["question"],
                        "target_concept": decision["target_concept"],
                        "reason": decision["reason"],
                        "source": decision["source"],
                    }
                )
                self._sessions.advance(session_id, InterviewState.FOLLOW_UP)
                self._sessions.update_context(session_id, context)
                self._persist_interviewer(
                    session_id,
                    decision["question"],
                    question=current,
                    kind="follow_up",
                    extra={
                        "follow_up": {
                            "target_concept": decision["target_concept"],
                            "source": decision["source"],
                        }
                    },
                )
                return InterviewTurnResponse(reply=decision["question"], done=False)
        else:
            context["follow_up_count"] += 1
            context["primary_answered"] += 1
            context["pending_follow_up"] = None
            context["phase"] = "question"

        return self._advance_after_primary(session_id, context)

    # --- Turn decision --------------------------------------------------------

    def _decide_next(
        self,
        session_id: str,
        context: dict,
        question: dict,
        answer: str,
        score: float,
        missing: list[str],
        covered: list[str],
    ) -> dict:
        """Decide the action after one primary answer.

        With an AdaptiveDecider wired, it owns the decision (Gemini with a
        deterministic fallback). Otherwise the classic follow-up heuristic
        applies, then the plan length decides between advancing and completing.

        Returns ``{"action", "question", "target_concept", "reason", "source"}``
        where ``action`` is ``follow_up``, ``next_question``, or ``complete``.
        """
        remaining = len(context["plan"]["questions"]) - (context["primary_index"] + 1)

        if self._adaptive_decider is not None:
            topic = next(
                (t for t in context.get("topics", []) if t.get("id") == question.get("topic_id")),
                {},
            )
            decision = self._adaptive_decider.decide(
                session_id=session_id,
                topic=topic,
                question=question,
                answer=answer,
                evaluation={
                    "question_id": question["curriculum_question_id"],
                    "topic_id": question["topic_id"],
                    "kind": "primary",
                    "score": score,
                    "missing": missing,
                    "covered": covered,
                },
                conversation_context=self._memory.get_conversation_history(session_id),
                remaining_questions=remaining,
                difficulty_bias=context.get("difficulty_bias"),
            )
            # The engine is authoritative over the plan length: never complete
            # early, never skip ahead of the final question.
            if decision.action == ACTION_COMPLETE and remaining > 0:
                decision = self._coerce(
                    decision, ACTION_NEXT, "Engine corrected a premature complete."
                )
            elif decision.action in (ACTION_NEXT, ACTION_FOLLOW_UP) and remaining <= 0:
                decision = self._coerce(
                    decision, ACTION_COMPLETE, "Engine corrected: no questions remain."
                )
            return {
                "action": decision.action,
                "question": decision.question,
                "target_concept": decision.target_concept,
                "reason": decision.reason,
                "source": decision.source,
            }

        follow_up = self._plan_follow_up(
            session_id,
            context,
            question,
            answer,
            score,
            missing,
            covered,
        )
        if follow_up is not None:
            return {
                "action": ACTION_FOLLOW_UP,
                "question": follow_up["question"],
                "target_concept": follow_up["target_concept"],
                "reason": follow_up["reason"],
                "source": follow_up["source"],
            }
        if remaining <= 0:
            return {
                "action": ACTION_COMPLETE,
                "question": "",
                "target_concept": None,
                "reason": "deterministic: no questions remain",
                "source": "deterministic",
            }
        return {
            "action": ACTION_NEXT,
            "question": "",
            "target_concept": None,
            "reason": "deterministic: proceed to next question",
            "source": "deterministic",
        }

    @staticmethod
    def _coerce(decision: InterviewDecision, action: str, reason: str) -> InterviewDecision:
        """Return ``decision`` rewritten to ``action`` (preserves ``source``)."""
        return replace_decision(
            decision,
            action=action,
            reason=reason,
            question="",
            target_concept=None,
        )

    def _plan_follow_up(
        self,
        session_id: str,
        context: dict,
        question: dict,
        answer: str,
        score: float,
        missing: list[str],
        covered: list[str],
    ) -> dict | None:
        """Decide whether to ask exactly one follow-up for a primary answer.

        When a FollowUpAdvisor is wired it owns the decision (Gemini with a
        deterministic fallback); otherwise the classic heuristic applies. Returns
        ``None`` when no follow-up should be asked. Never allows a follow-up when
        the plan forbids one (``follow_up_allowed``), so coverage is preserved.
        """
        if not question.get("follow_up_allowed", False):
            return None

        if self._follow_up_advisor is not None:
            topic = next(
                (t for t in context.get("topics", []) if t.get("id") == question.get("topic_id")),
                {},
            )
            decision = self._follow_up_advisor.decide(
                session_id=session_id,
                topic=topic,
                question=question,
                answer=answer,
                evaluation={
                    "question_id": question["curriculum_question_id"],
                    "topic_id": question["topic_id"],
                    "kind": "primary",
                    "score": score,
                    "missing": missing,
                    "covered": covered,
                },
                conversation_context=self._memory.get_conversation_history(session_id),
            )
            if not decision.should_follow_up:
                return None
            return {
                "question": decision.question,
                "target_concept": decision.target_concept,
                "reason": decision.reason,
                "source": decision.source,
            }

        if not missing:
            return None
        concept = missing[0]
        return {
            "question": self._build_follow_up(question, concept),
            "target_concept": concept,
            "reason": "deterministic: expected concept not addressed",
            "source": "deterministic",
        }

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

        return self._complete(session_id, context)

    def _complete(self, session_id: str, context: dict) -> InterviewTurnResponse:
        """Finish the interview: SUMMARY -> COMPLETED, generate the report."""
        # Final answer: QUESTION/FOLLOW_UP -> SUMMARY -> COMPLETED.
        self._sessions.advance(session_id, InterviewState.SUMMARY)
        self._sessions.complete(session_id)
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
        extra: dict | None = None,
    ) -> None:
        metadata = {"kind": kind}
        if question:
            metadata["question_id"] = question["curriculum_question_id"]
            metadata["topic_id"] = question["topic_id"]
        if extra:
            metadata.update(extra)
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
        greeting = (
            f"Welcome, {candidate.name}! This is your InterVue AI technical interview. "
            f"You will be asked {plan.total_questions} questions across "
            f"{len(plan.topics_covered)} topics."
        )
        if plan.difficulty_bias:
            label = {
                "easy": "a junior-friendly",
                "hard": "a senior-level",
            }.get(plan.difficulty_bias, "a balanced")
            greeting += f" We've tuned the questions for {label} difficulty."
        return greeting + " Let's begin."

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
        """Map the persisted report plus context into the response feedback.

        Items in ``report.improvements`` prefixed with ``NEXT_STEP_PREFIX`` are
        AI-generated next steps and surface in the response ``next`` list rather
        than as gaps. The deterministic report never emits that prefix, so the
        deterministic mapping is unchanged.
        """
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

        gaps: list[str] = []
        for item in report.improvements:
            if item.startswith(NEXT_STEP_PREFIX):
                step = item[len(NEXT_STEP_PREFIX):].strip()
                if step and step not in next_steps:
                    next_steps.insert(0, step)
            else:
                gaps.append(item)

        return InterviewFeedback(
            summary=report.summary,
            strengths=list(report.strengths),
            gaps=gaps,
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
