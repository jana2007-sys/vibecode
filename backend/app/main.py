"""FastAPI application factory for InterVue AI.

Wire order matters:
  1. configuration  -> logging
  2. database        -> schema initialization
  3. middleware      -> CORS, error handling
  4. routers         -> HTTP endpoints
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.middleware import setup_error_handlers, setup_middleware
from app.api.routes import health, interview, sessions
from app.database.connection import Database, get_database
from app.utils.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Adaptive AI Technical Interview Agent — API.",
    )

    setup_middleware(app, settings)
    setup_error_handlers(app)

    # Initialize the database (creates schema on first run).
    db: Database = get_database()
    db.initialize()

    # Register routers.
    api_prefix = "/api"
    app.include_router(health.router, prefix=api_prefix, tags=["health"])
    app.include_router(interview.router, prefix=api_prefix, tags=["interview"])
    app.include_router(sessions.router, prefix=api_prefix, tags=["sessions"])

    logger.info("Application '%s' ready (env=%s)", settings.app_name, settings.app_env)
    return app


app = create_app()
