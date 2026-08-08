"""Structured feedback / report generation.

Assembles the final interview report from aggregated scores and the session
context, and persists it for retrieval. Reporting is currently deterministic
(thresholds over per-topic averages plus recurring missing concepts); Gemini
narrative will be layered on later.

Collaborators: EvaluationEngine, ScoreRepository, FeedbackRepository,
SessionRepository, GeminiService.
"""

from __future__ import annotations

from collections import Counter

from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.models.common import new_uuid, utc_now
from app.models.feedback import FeedbackRead, TopicSummary
from app.services.evaluation_engine import EvaluationEngine
from app.services.gemini_service import GeminiService
from app.utils.errors import NotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Topic averages at/above this count as a strength.
STRENGTH_THRESHOLD = 6.5
#: Topic averages below this count as a gap.
GAP_THRESHOLD = 5.0
#: How many recurring missing concepts to surface in the report.
MAX_MISSING_CONCEPTS = 3


class FeedbackGenerator:
    """Produces the final structured interview report."""

    def __init__(
        self,
        evaluation_engine: EvaluationEngine,
        score_repository: ScoreRepository,
        feedback_repository: FeedbackRepository,
        gemini_service: GeminiService,
        session_repository: SessionRepository,
    ) -> None:
        self._evaluator = evaluation_engine
        self._scores = score_repository
        self._feedback = feedback_repository
        self._gemini = gemini_service
        self._sessions = session_repository

    def generate_report(self, session_id: str) -> FeedbackRead:
        """Build and persist the full report for a session.

        Deterministic: aggregates the session's recorded scores per topic,
        derives strengths/gaps from threshold averages, and appends the most
        frequently missed concepts to the improvements list.
        """
        session = self._sessions.get_by_id(session_id)
        if session is None:
            raise NotFoundError(f"Session {session_id} not found")

        context = self._sessions.loads_json(session.get("context"), {})
        scores = self._scores.list_by_session(session_id)
        topic_titles = {topic.get("id"): topic.get("title", "") for topic in context.get("topics", [])}

        topic_scores: dict[str, list[float]] = {}
        for row in scores:
            topic_scores.setdefault(row["topic_id"], []).append(float(row["score"]))

        topic_summaries = [
            TopicSummary(
                topic_id=topic_id,
                title=topic_titles.get(topic_id, topic_id),
                average_score=round(sum(values) / len(values), 2),
            )
            for topic_id, values in topic_scores.items()
        ]

        all_scores = [float(row["score"]) for row in scores]
        overall = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0

        strengths = [
            f"{topic.title} ({topic.average_score:.1f}/10)"
            for topic in topic_summaries
            if topic.average_score >= STRENGTH_THRESHOLD
        ]
        improvements = [
            f"{topic.title} ({topic.average_score:.1f}/10)"
            for topic in topic_summaries
            if topic.average_score < GAP_THRESHOLD
        ]
        improvements.extend(self._recurring_missing_concepts(context, MAX_MISSING_CONCEPTS))

        summary = (
            f"Interview complete: {len(scores)} answer(s) across "
            f"{len(topic_summaries)} topic(s) with an overall score of {overall:.1f}/10."
        )

        feedback_id = new_uuid()
        created_at = utc_now()
        self._feedback.create(
            feedback_id=feedback_id,
            session_id=session_id,
            overall_score=overall,
            summary=summary,
            strengths=strengths,
            improvements=improvements,
            topics=[topic.model_dump(mode="json") for topic in topic_summaries],
            created_at=created_at,
        )
        logger.info(
            "Generated report %s for session %s (overall %.2f)",
            feedback_id,
            session_id,
            overall,
        )
        return FeedbackRead(
            id=feedback_id,
            session_id=session_id,
            overall_score=overall,
            summary=summary,
            strengths=strengths,
            improvements=improvements,
            topics=topic_summaries,
            created_at=created_at,
        )

    @staticmethod
    def _recurring_missing_concepts(context: dict, limit: int) -> list[str]:
        """Return the most frequently missed concepts across the session."""
        counter: Counter[str] = Counter()
        for evaluation in context.get("evaluations", []):
            counter.update(evaluation.get("missing", []))
        return [f"Review: {concept}" for concept, _ in counter.most_common(limit)]
