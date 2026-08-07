"""Interview orchestration.

Top-level coordinator for the conversation loop: moves the session through the
state machine, asks questions, collects answers, and hands results to the
evaluation and feedback services.

Collaborators: SessionManager, QuestionPlanner, EvaluationEngine, MemoryEngine.
"""

from __future__ import annotations

from app.services.evaluation_engine import EvaluationEngine
from app.services.memory_engine import MemoryEngine
from app.services.question_planner import QuestionPlanner
from app.services.session_manager import SessionManager
from app.utils.logging import get_logger

logger = get_logger(__name__)


class InterviewEngine:
    """Runs one adaptive interview conversation."""

    def __init__(
        self,
        session_manager: SessionManager,
        question_planner: QuestionPlanner,
        evaluation_engine: EvaluationEngine,
        memory_engine: MemoryEngine,
    ) -> None:
        self._sessions = session_manager
        self._planner = question_planner
        self._evaluator = evaluation_engine
        self._memory = memory_engine

    def start(self, session_id: str) -> str:
        """Begin an interview: emit the introduction message.

        Placeholder: returns the first interviewer turn.
        """
        raise NotImplementedError("Interview orchestration will be implemented later.")

    def handle_answer(self, session_id: str, answer: str) -> str:
        """Process a candidate answer and return the next interviewer turn.

        Placeholder: will store the answer, optionally evaluate it, and decide
        between a follow-up, a new question, or advancing the topic.
        """
        raise NotImplementedError("Interview orchestration will be implemented later.")

    def finish(self, session_id: str) -> None:
        """Wrap up the interview and trigger feedback generation.

        Placeholder: will transition to SUMMARY then COMPLETED and call the
        FeedbackGenerator.
        """
        raise NotImplementedError("Interview orchestration will be implemented later.")
