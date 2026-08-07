"""Cross-cutting HTTP concerns: CORS, request logging, error mapping.

Keeps the FastAPI app factory clean by hiding middleware/exception wiring.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.utils.config import Settings
from app.utils.errors import InterVueError
from app.utils.logging import get_logger

logger = get_logger(__name__)


def setup_middleware(app: FastAPI, settings: Settings) -> None:
    """Register all middleware on the given app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log every request with status code and latency."""
        import time

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


def setup_error_handlers(app: FastAPI) -> None:
    """Register handlers that translate domain exceptions into JSON responses."""

    @app.exception_handler(InterVueError)
    async def handle_intervue_error(_: Request, exc: InterVueError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )
