"""Private archive of enrolled candidates and their completed reports.

``EnrollmentStore`` is the write-side of the private database: when an enrolled
(custom-*) candidate completes an interview, it snapshots their profile and
stores the full ``ReportRead`` payload into the private SQLite file. Predefined
seeded profiles (``candidate-*``) never enrolled, so they are never archived.
"""

from __future__ import annotations

from app.database.repositories.candidate_repository import CandidateRepository
from app.database.repositories.enrollment_repository import EnrollmentRepository
from app.models.candidate import is_custom_profile
from app.models.common import utc_now
from app.services.report_service import ReportService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class EnrollmentStore:
    """Archives enrolled candidates + their reports into the private database."""

    def __init__(
        self,
        repository: EnrollmentRepository,
        report_service: ReportService,
        candidate_repository: CandidateRepository,
    ) -> None:
        self._repository = repository
        self._reports = report_service
        self._candidates = candidate_repository

    def archive_completed_interview(self, candidate_id: str, session_id: str) -> bool:
        """Archive a completed interview for an enrolled candidate.

        Stores a snapshot of the candidate profile plus the full report for
        ``session_id``. Returns ``True`` when archived; ``False`` when the
        candidate is unknown or is a predefined (non-enrolled) profile.
        """
        candidate = self._candidates.get_by_id(candidate_id)
        if candidate is None or not is_custom_profile(candidate_id):
            return False
        report = self._reports.get_report(candidate_id, session_id)
        self._repository.store(
            candidate=candidate,
            report=report.model_dump(mode="json"),
            now=utc_now(),
        )
        logger.info(
            "Archived enrolled candidate %s report for session %s",
            candidate_id,
            session_id,
        )
        return True
