"""Structured feedback / report generation.

Assembles the final interview report from aggregated scores and transcripts,
and persists it for retrieval.

Collaborators: EvaluationEngine, ScoreRepository, FeedbackRepository, GeminiService.
"""

from __future__ import annotations

from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.score_repository import ScoreRepository
from app.models.feedback import FeedbackRead
from app.services.evaluation_engine import EvaluationEngine
from app.services.gemini_service import GeminiService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class FeedbackGenerator:
    """Produces the final structured interview report."""

    def __init__(
        self,
        evaluation_engine: EvaluationEngine,
        score_repository: ScoreRepository,
        feedback_repository: FeedbackRepository,
        gemini_service: GeminiService,
    ) -> None:
        self._evaluator = evaluation_engine
        self._scores = score_repository
        self._feedback = feedback_repository
        self._gemini = gemini_service

    def generate_report(self, session_id: str) -> FeedbackRead:
        """Build and persist the full report for a session.

        Placeholder: will aggregate scores, ask Gemini for narrative feedback,
        and persist the resulting FeedbackRead.
        """
        raise NotImplementedError("Report generation will be implemented later.")
