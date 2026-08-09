"""Dependency injection wiring.

FastAPI dependencies live here so that routes stay free of construction logic.
Swap implementations here (e.g. a different repository backend) without touching
routes or services.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.database.connection import Database, get_database, get_private_database
from app.database.repositories.candidate_repository import CandidateRepository
from app.database.repositories.enrollment_repository import EnrollmentRepository
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.memory.conversation_memory import ConversationMemory
from app.services.adaptive_decider import AdaptiveDecider
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.enrollment_store import EnrollmentStore
from app.services.evaluation_engine import EvaluationEngine
from app.services.feedback_generator import FeedbackGenerator
from app.services.follow_up_advisor import FollowUpAdvisor
from app.services.gemini_service import GeminiService
from app.services.interview_engine import InterviewEngine
from app.services.memory_engine import MemoryEngine
from app.services.prompt_builder import PromptBuilder
from app.services.question_planner import QuestionPlanner
from app.services.report_service import ReportService
from app.services.session_manager import SessionManager
from app.services.verification_service import AIVerifierEnsemble
from app.utils.config import get_settings


def get_session_repository(
    db: Annotated[Database, Depends(get_database)],
) -> SessionRepository:
    """Provide a SessionRepository bound to the application database."""
    return SessionRepository(db)


def get_candidate_repository(
    db: Annotated[Database, Depends(get_database)],
) -> CandidateRepository:
    """Provide a CandidateRepository bound to the application database."""
    return CandidateRepository(db)


def get_message_repository(
    db: Annotated[Database, Depends(get_database)],
) -> MessageRepository:
    """Provide a MessageRepository bound to the application database."""
    return MessageRepository(db)


def get_score_repository(
    db: Annotated[Database, Depends(get_database)],
) -> ScoreRepository:
    """Provide a ScoreRepository bound to the application database."""
    return ScoreRepository(db)


def get_feedback_repository(
    db: Annotated[Database, Depends(get_database)],
) -> FeedbackRepository:
    """Provide a FeedbackRepository bound to the application database."""
    return FeedbackRepository(db)


def get_enrollment_repository(
    db: Annotated[Database, Depends(get_private_database)],
) -> EnrollmentRepository:
    """Provide an EnrollmentRepository bound to the private database."""
    return EnrollmentRepository(db)


def get_enrollment_store(
    repository: Annotated[EnrollmentRepository, Depends(get_enrollment_repository)],
    report_service: Annotated[ReportService, Depends(get_report_service)],
    candidate_repository: Annotated[CandidateRepository, Depends(get_candidate_repository)],
) -> EnrollmentStore:
    """Provide the private archive for enrolled candidates' completed reports."""
    return EnrollmentStore(
        repository=repository,
        report_service=report_service,
        candidate_repository=candidate_repository,
    )


def get_report_service(
    candidate_repository: Annotated[CandidateRepository, Depends(get_candidate_repository)],
    session_repository: Annotated[SessionRepository, Depends(get_session_repository)],
    message_repository: Annotated[MessageRepository, Depends(get_message_repository)],
    feedback_repository: Annotated[FeedbackRepository, Depends(get_feedback_repository)],
    score_repository: Annotated[ScoreRepository, Depends(get_score_repository)],
) -> ReportService:
    """Provide the ReportService for history and report queries."""
    return ReportService(
        candidate_repository=candidate_repository,
        session_repository=session_repository,
        message_repository=message_repository,
        feedback_repository=feedback_repository,
        score_repository=score_repository,
    )


def get_session_manager(
    sessions: Annotated[SessionRepository, Depends(get_session_repository)],
) -> SessionManager:
    """Provide the top-level SessionManager service."""
    return SessionManager(session_repository=sessions)


def get_curriculum_loader() -> CurriculumLoader:
    """Provide the CurriculumLoader backed by the shipped curriculum data."""
    return CurriculumLoader()


def get_candidate_analyzer() -> CandidateAnalyzer:
    """Provide the CandidateAnalyzer backed by the shipped candidate data."""
    return CandidateAnalyzer()


def get_gemini_service() -> GeminiService:
    """Provide the Gemini client (inert until explicitly enabled)."""
    return GeminiService(get_settings())


def get_ai_verifier(
    gemini_service: Annotated[GeminiService, Depends(get_gemini_service)],
    prompt_builder: Annotated[PromptBuilder, Depends(get_prompt_builder)],
) -> AIVerifierEnsemble | None:
    """Provide the multi-AI answer verifier panel, or ``None`` when unconfigured.

    Enabled only when ``AI_VERIFIER_MODELS`` lists one or more model ids (the
    underlying Gemini integration must also be enabled). When unconfigured the
    EvaluationEngine falls back to single-model semantic evaluation, then to the
    deterministic scorer.
    """
    settings = get_settings()
    models = settings.ai_verifier_model_list
    if not models:
        return None
    return AIVerifierEnsemble(
        gemini_service=gemini_service,
        prompt_builder=prompt_builder,
        models=models,
        agreement_threshold=settings.ai_verifier_agreement,
    )


def get_prompt_builder() -> PromptBuilder:
    """Provide the prompt builder backed by the shipped prompt templates."""
    return PromptBuilder()


def get_follow_up_advisor(
    prompt_builder: Annotated[PromptBuilder, Depends(get_prompt_builder)],
    gemini_service: Annotated[GeminiService, Depends(get_gemini_service)],
) -> FollowUpAdvisor:
    """Provide the adaptive follow-up advisor (deterministic fallback built in)."""
    return FollowUpAdvisor(
        prompt_builder=prompt_builder,
        gemini_service=gemini_service,
    )


def get_adaptive_decider(
    prompt_builder: Annotated[PromptBuilder, Depends(get_prompt_builder)],
    gemini_service: Annotated[GeminiService, Depends(get_gemini_service)],
    follow_up_advisor: Annotated[FollowUpAdvisor, Depends(get_follow_up_advisor)],
) -> AdaptiveDecider:
    """Provide the per-turn adaptive interview decider.

    Decides follow-up vs. next-question vs. completion after every primary
    answer (Gemini with a deterministic fallback; follow-up text grounded via
    the FollowUpAdvisor). The engine stays authoritative over plan length.
    """
    return AdaptiveDecider(
        prompt_builder=prompt_builder,
        gemini_service=gemini_service,
        follow_up_advisor=follow_up_advisor,
    )


def get_conversation_memory() -> ConversationMemory:
    """Provide a fresh in-memory conversation store."""
    return ConversationMemory()


def get_memory_engine(
    memory: Annotated[ConversationMemory, Depends(get_conversation_memory)],
    gemini_service: Annotated[GeminiService, Depends(get_gemini_service)],
    session_repository: Annotated[SessionRepository, Depends(get_session_repository)],
    message_repository: Annotated[MessageRepository, Depends(get_message_repository)],
    score_repository: Annotated[ScoreRepository, Depends(get_score_repository)],
    feedback_repository: Annotated[FeedbackRepository, Depends(get_feedback_repository)],
) -> MemoryEngine:
    """Provide the MemoryEngine: live window + durable session memory."""
    return MemoryEngine(
        conversation_memory=memory,
        gemini_service=gemini_service,
        session_repository=session_repository,
        message_repository=message_repository,
        score_repository=score_repository,
        feedback_repository=feedback_repository,
    )


def get_question_planner(
    curriculum_loader: Annotated[CurriculumLoader, Depends(get_curriculum_loader)],
    candidate_analyzer: Annotated[CandidateAnalyzer, Depends(get_candidate_analyzer)],
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> QuestionPlanner:
    """Provide the QuestionPlanner used to build interview plans.

    The planner runs in development mode unless the app is explicitly running in
    production. Development mode waives the production minimums (at least 4
    usable topics / 8 questions) so the shipped in-progress curriculum can be
    previewed end-to-end; such plans are flagged via ``is_complete``.
    """
    settings = get_settings()
    return QuestionPlanner(
        curriculum_loader=curriculum_loader,
        candidate_analyzer=candidate_analyzer,
        memory_engine=memory_engine,
        development_mode=settings.app_env != "production",
    )


def get_evaluation_engine(
    gemini_service: Annotated[GeminiService, Depends(get_gemini_service)],
    score_repository: Annotated[ScoreRepository, Depends(get_score_repository)],
    message_repository: Annotated[MessageRepository, Depends(get_message_repository)],
    prompt_builder: Annotated[PromptBuilder, Depends(get_prompt_builder)],
    verifier: Annotated[AIVerifierEnsemble | None, Depends(get_ai_verifier)] = None,
) -> EvaluationEngine:
    """Provide the EvaluationEngine that scores candidate answers.

    When a multi-AI verifier panel is configured, each answer is cross-checked
    by the panel before grading; otherwise a single Gemini semantic evaluation
    is layered on the deterministic scorer.
    """
    return EvaluationEngine(
        gemini_service=gemini_service,
        score_repository=score_repository,
        message_repository=message_repository,
        prompt_builder=prompt_builder,
        verifier=verifier,
    )


def get_feedback_generator(
    evaluation_engine: Annotated[EvaluationEngine, Depends(get_evaluation_engine)],
    score_repository: Annotated[ScoreRepository, Depends(get_score_repository)],
    feedback_repository: Annotated[FeedbackRepository, Depends(get_feedback_repository)],
    gemini_service: Annotated[GeminiService, Depends(get_gemini_service)],
    session_repository: Annotated[SessionRepository, Depends(get_session_repository)],
    prompt_builder: Annotated[PromptBuilder, Depends(get_prompt_builder)],
) -> FeedbackGenerator:
    """Provide the FeedbackGenerator that produces the final report."""
    return FeedbackGenerator(
        evaluation_engine=evaluation_engine,
        score_repository=score_repository,
        feedback_repository=feedback_repository,
        gemini_service=gemini_service,
        session_repository=session_repository,
        prompt_builder=prompt_builder,
    )


def get_interview_engine(
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    question_planner: Annotated[QuestionPlanner, Depends(get_question_planner)],
    evaluation_engine: Annotated[EvaluationEngine, Depends(get_evaluation_engine)],
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
    curriculum_loader: Annotated[CurriculumLoader, Depends(get_curriculum_loader)],
    candidate_analyzer: Annotated[CandidateAnalyzer, Depends(get_candidate_analyzer)],
    feedback_generator: Annotated[FeedbackGenerator, Depends(get_feedback_generator)],
    message_repository: Annotated[MessageRepository, Depends(get_message_repository)],
    follow_up_advisor: Annotated[FollowUpAdvisor, Depends(get_follow_up_advisor)],
    adaptive_decider: Annotated[AdaptiveDecider, Depends(get_adaptive_decider)],
    candidate_repository: Annotated[CandidateRepository, Depends(get_candidate_repository)],
    enrollment_store: Annotated[EnrollmentStore, Depends(get_enrollment_store)],
) -> InterviewEngine:
    """Provide the top-level InterviewEngine for the interactive contract."""
    return InterviewEngine(
        session_manager,
        question_planner,
        evaluation_engine,
        memory_engine,
        curriculum_loader=curriculum_loader,
        candidate_analyzer=candidate_analyzer,
        feedback_generator=feedback_generator,
        message_repository=message_repository,
        follow_up_advisor=follow_up_advisor,
        adaptive_decider=adaptive_decider,
        candidate_repository=candidate_repository,
        enrollment_store=enrollment_store,
    )


SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]
CandidateRepositoryDep = Annotated[CandidateRepository, Depends(get_candidate_repository)]
ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]
MessageRepositoryDep = Annotated[MessageRepository, Depends(get_message_repository)]
ScoreRepositoryDep = Annotated[ScoreRepository, Depends(get_score_repository)]
FeedbackRepositoryDep = Annotated[FeedbackRepository, Depends(get_feedback_repository)]
InterviewEngineDep = Annotated[InterviewEngine, Depends(get_interview_engine)]
