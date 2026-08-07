"""Candidate answer evaluation.

Scores a candidate's answer for a given question, producing per-question and
per-topic scores. The scoring itself will be delegated to the LLM (GeminiService)
once enabled; this class owns the orchestration and persistence.

Collaborators: GeminiService, ScoreRepository, MessageRepository.
"""

from __future__ import annotations

from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.services.gemini_service import GeminiService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class EvaluationEngine:
    """Evaluates candidate answers and persists scores."""

    def __init__(
        self,
        gemini_service: GeminiService,
        score_repository: ScoreRepository,
        message_repository: MessageRepository,
    ) -> None:
        self._gemini = gemini_service
        self._scores = score_repository
        self._messages = message_repository

    def evaluate_answer(
        self,
        session_id: str,
        question_id: str,
        answer: str,
    ) -> float:
        """Score a single answer on a 0-10 scale.

        Placeholder: will call GeminiService to score and rationalize, then
        persist via ScoreRepository.
        """
        raise NotImplementedError("Answer evaluation will be implemented later.")

    def evaluate_topic(self, session_id: str, topic_id: str) -> float:
        """Aggregate per-question scores into a topic score.

        Placeholder: will weight individual scores per curriculum config.
        """
        raise NotImplementedError("Topic evaluation will be implemented later.")
