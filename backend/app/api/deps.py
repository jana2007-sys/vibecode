"""Dependency injection wiring.

FastAPI dependencies live here so that routes stay free of construction logic.
Swap implementations here (e.g. a different repository backend) without touching
routes or services.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.database.connection import Database, get_database
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.score_repository import ScoreRepository
from app.database.repositories.session_repository import SessionRepository
from app.services.session_manager import SessionManager


def get_session_repository(
    db: Annotated[Database, Depends(get_database)],
) -> SessionRepository:
    """Provide a SessionRepository bound to the application database."""
    return SessionRepository(db)


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


def get_session_manager(
    sessions: Annotated[SessionRepository, Depends(get_session_repository)],
) -> SessionManager:
    """Provide the top-level SessionManager service."""
    return SessionManager(session_repository=sessions)


SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]
MessageRepositoryDep = Annotated[MessageRepository, Depends(get_message_repository)]
ScoreRepositoryDep = Annotated[ScoreRepository, Depends(get_score_repository)]
FeedbackRepositoryDep = Annotated[FeedbackRepository, Depends(get_feedback_repository)]
