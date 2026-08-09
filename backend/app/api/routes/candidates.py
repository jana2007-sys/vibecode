"""Candidate profile, history, and report endpoints.

Candidates are the persisted counterpart to the interview wire ``CandidateProfile``:
they add ``email`` and ``strengths``. History and reports are read-only views over
the persisted sessions/feedback owned by a candidate.

Deletion rules: profiles added through this API (ids prefixed ``custom-``) can be
deleted and their history cleared; the predefined seeded profiles are read-only
so their history may be cleared but the profile itself cannot be removed.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import (
    CandidateRepositoryDep,
    ReportServiceDep,
    SessionRepositoryDep,
)
from app.models.candidate import (
    CandidateCreate,
    CandidateList,
    CandidateRead,
    DeleteResult,
    is_custom_profile,
)
from app.models.common import new_uuid, utc_now
from app.models.report import InterviewHistory, ReportRead
from app.utils.errors import NotFoundError, PermissionError

router = APIRouter()


@router.get("/candidates", response_model=CandidateList)
async def list_candidates(
    candidate_repository: CandidateRepositoryDep,
) -> CandidateList:
    """List all persisted candidates, alphabetically by name."""
    rows = candidate_repository.list_all()
    items = [CandidateRead(**row, is_custom=is_custom_profile(row["id"])) for row in rows]
    return CandidateList(items=items, total=len(items))


@router.post("/candidates", response_model=CandidateRead)
async def create_candidate(
    body: CandidateCreate,
    response: Response,
    candidate_repository: CandidateRepositoryDep,
) -> CandidateRead:
    """Create a candidate profile (or update the row with the same email).

    Responds ``201`` when a new candidate is created and ``200`` when an existing
    email was updated in place.
    """
    existing = candidate_repository.get_by_email(body.email)
    candidate_id = existing["id"] if existing else f"custom-{new_uuid()}"
    now = utc_now()
    candidate_repository.upsert(
        candidate_id=candidate_id,
        name=body.name,
        email=body.email,
        role=body.role,
        years_of_experience=body.years_of_experience,
        experience_level=body.experience_level,
        skills=[skill.model_dump(mode="json") for skill in body.skills],
        learning_journey=[entry.model_dump(mode="json") for entry in body.learning_journey],
        preferred_languages=body.preferred_languages,
        focus_areas=body.focus_areas,
        strengths=body.strengths,
        notes=body.notes,
        now=now,
    )
    response.status_code = 201 if existing is None else 200
    row = candidate_repository.get_by_id(candidate_id)
    return CandidateRead(**row, is_custom=is_custom_profile(candidate_id))


@router.delete("/candidates/{candidate_id}", response_model=DeleteResult)
async def delete_candidate(
    candidate_id: str,
    candidate_repository: CandidateRepositoryDep,
    session_repository: SessionRepositoryDep,
) -> DeleteResult:
    """Delete an API-added candidate and all of their interview data.

    Predefined seeded candidates are protected: only profiles added through the
    API (custom-* ids) can be deleted.
    """
    row = candidate_repository.get_by_id(candidate_id)
    if row is None:
        raise NotFoundError(f"Candidate {candidate_id} not found")
    if not is_custom_profile(candidate_id):
        raise PermissionError(
            f"Candidate {candidate_id} is a predefined profile and cannot be deleted"
        )
    deleted_sessions = session_repository.delete_by_candidate(candidate_id)
    candidate_repository.delete_by_id(candidate_id)
    return DeleteResult(deleted=True, deleted_sessions=deleted_sessions)


@router.delete("/candidates/{candidate_id}/interviews", response_model=DeleteResult)
async def clear_candidate_history(
    candidate_id: str,
    candidate_repository: CandidateRepositoryDep,
    session_repository: SessionRepositoryDep,
) -> DeleteResult:
    """Delete every interview session (and its data) for a candidate."""
    row = candidate_repository.get_by_id(candidate_id)
    if row is None:
        raise NotFoundError(f"Candidate {candidate_id} not found")
    deleted_sessions = session_repository.delete_by_candidate(candidate_id)
    return DeleteResult(deleted=True, deleted_sessions=deleted_sessions)


@router.get("/candidates/{candidate_id}/interviews", response_model=InterviewHistory)
async def get_candidate_history(
    candidate_id: str,
    report_service: ReportServiceDep,
) -> InterviewHistory:
    """List every interview for a candidate, newest first."""
    return report_service.get_history(candidate_id)


@router.get(
    "/candidates/{candidate_id}/interviews/{session_id}/report",
    response_model=ReportRead,
)
async def get_session_report(
    candidate_id: str,
    session_id: str,
    report_service: ReportServiceDep,
) -> ReportRead:
    """Fetch the full persisted report for one of a candidate's sessions."""
    return report_service.get_report(candidate_id, session_id)


@router.get(
    "/candidates/{candidate_id}/interviews/{session_id}/report/pdf",
    response_model=None,
)
async def get_session_report_pdf(
    candidate_id: str,
    session_id: str,
    report_service: ReportServiceDep,
) -> Response:
    """Download the report for a session as a PDF document."""
    return _pdf_response(report_service, candidate_id, session_id)


@router.get("/interviews/{session_id}/report/pdf", response_model=None)
async def get_session_report_pdf_by_session(
    session_id: str,
    report_service: ReportServiceDep,
    session_repository: SessionRepositoryDep,
) -> Response:
    """Download a session's report as a PDF, resolving the owning candidate.

    Convenience alias of ``/candidates/{candidate_id}/interviews/{session_id}/report/pdf``
    when only the session id is known.
    """
    session = session_repository.get_by_id(session_id)
    if session is None:
        raise NotFoundError(f"Session {session_id} not found")
    return _pdf_response(report_service, session["candidate_id"], session_id)


def _pdf_response(
    report_service: ReportServiceDep,
    candidate_id: str,
    session_id: str,
) -> Response:
    """Build the PDF download response for a session."""
    data = report_service.build_pdf_bytes(candidate_id, session_id)
    filename = f"intervue-report-{session_id}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
