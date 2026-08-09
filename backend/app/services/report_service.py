"""Report assembly and PDF export.

Reads persisted interview artifacts (session, transcript, feedback) and assembles
them into the ``ReportRead`` contract, or renders them into a downloadable PDF.
The service is a pure reader: it never mutates session state.

Collaborators: CandidateRepository, SessionRepository, MessageRepository,
FeedbackRepository.
"""

from __future__ import annotations

from app.database.repositories.candidate_repository import CandidateRepository
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.models.feedback import FeedbackRead
from app.models.message import MessageRole
from app.models.report import (
    AnswerReview,
    InterviewHistory,
    InterviewHistoryItem,
    ReportCandidate,
    ReportMessage,
    ReportRead,
)
from app.services.pdf_report import render_report_pdf
from app.utils.errors import NotFoundError, ValidationError


class ReportService:
    """Builds interview-history and full-report payloads from persisted rows."""

    def __init__(
        self,
        candidate_repository: CandidateRepository,
        session_repository: SessionRepository,
        message_repository: MessageRepository,
        feedback_repository: FeedbackRepository,
        score_repository: ScoreRepository,
    ) -> None:
        self._candidates = candidate_repository
        self._sessions = session_repository
        self._messages = message_repository
        self._feedback = feedback_repository
        self._scores = score_repository

    # --- History --------------------------------------------------------------

    def get_candidate(self, candidate_id: str) -> dict:
        """Return the candidate row, raising 404 when missing."""
        row = self._candidates.get_by_id(candidate_id)
        if row is None:
            raise NotFoundError(f"Candidate {candidate_id} not found")
        return row

    def get_history(self, candidate_id: str) -> InterviewHistory:
        """Return every interview session for a candidate, newest first."""
        self.get_candidate(candidate_id)
        rows = self._sessions.list_by_candidate(candidate_id)
        items = []
        for row in rows:
            feedback = self._feedback.get_by_session(row["id"])
            items.append(
                InterviewHistoryItem(
                    session_id=row["id"],
                    state=row["state"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    completed_at=row.get("completed_at"),
                    overall_score=feedback["overall_score"] if feedback else None,
                    summary=feedback["summary"] if feedback else "",
                )
            )
        return InterviewHistory(candidate_id=candidate_id, items=items, total=len(items))

    # --- Full report ----------------------------------------------------------

    def _build_answer_reviews(
        self,
        session_id: str,
        messages: list[ReportMessage],
        topic_titles: dict[str, str],
    ) -> list[AnswerReview]:
        """Pair every graded question with its transcript question/answer.

        Scores are deduplicated by ``question_id`` (keeping the last recorded
        evaluation) so repeated evaluations of the same question collapse into
        a single review row.
        """
        reviews: list[AnswerReview] = []
        by_question: dict[str, dict] = {}
        for row in self._scores.list_by_session(session_id):
            by_question[row["question_id"]] = row

        def first_for(role: str, question_id: str) -> str:
            for message in messages:
                if message.role == role and message.metadata.get("question_id") == question_id:
                    return message.content
            return ""

        for question_id, score_row in by_question.items():
            score = float(score_row["score"])
            reviews.append(
                AnswerReview(
                    question_id=question_id,
                    topic_id=score_row.get("topic_id", ""),
                    topic_title=topic_titles.get(score_row.get("topic_id", ""), ""),
                    question=first_for(MessageRole.INTERVIEWER.value, question_id),
                    answer=first_for(MessageRole.CANDIDATE.value, question_id),
                    score=score,
                    rationale=score_row.get("rationale", ""),
                    verdict="Very good" if score > 8 else "Needs improvement",
                )
            )
        return reviews

    def get_report(self, candidate_id: str, session_id: str) -> ReportRead:
        """Assemble the full report for a session owned by the candidate."""
        session = self._sessions.get_by_id(session_id)
        if session is None:
            raise NotFoundError(f"Session {session_id} not found")
        if session["candidate_id"] != candidate_id:
            raise NotFoundError(f"Session {session_id} does not belong to candidate {candidate_id}")

        candidate = self.get_candidate(candidate_id)
        feedback_row = self._feedback.get_by_session(session_id)
        if feedback_row is None:
            raise NotFoundError(f"No report has been generated for session {session_id}")

        messages = [
            ReportMessage(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                metadata=row.get("metadata", {}),
                created_at=row["created_at"],
            )
            for row in self._messages.list_by_session(session_id)
        ]

        feedback = FeedbackRead(
            id=feedback_row["id"],
            session_id=feedback_row["session_id"],
            overall_score=feedback_row["overall_score"],
            summary=feedback_row["summary"],
            strengths=feedback_row["strengths"],
            improvements=feedback_row["improvements"],
            topics=feedback_row["topics"],
            created_at=feedback_row["created_at"],
            source=feedback_row["source"],
        )

        topic_titles = {topic.topic_id: topic.title for topic in feedback.topics}

        return ReportRead(
            session_id=session_id,
            candidate=ReportCandidate(
                id=candidate["id"],
                name=candidate["name"],
                role=candidate.get("role", ""),
                email=candidate.get("email"),
                strengths=candidate.get("strengths", []),
            ),
            feedback=feedback,
            completed_at=session.get("completed_at"),
            messages=messages,
            answer_reviews=self._build_answer_reviews(session_id, messages, topic_titles),
        )

    # --- PDF ------------------------------------------------------------------

    def build_pdf_bytes(self, candidate_id: str, session_id: str) -> bytes:
        """Render the report for a session as PDF bytes."""
        report = self.get_report(candidate_id, session_id)
        try:
            return render_report_pdf(report)
        except Exception as exc:  # noqa: BLE001 - surface a friendly API error
            raise ValidationError("Could not render the PDF report.") from exc
