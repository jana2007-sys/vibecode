"""Liveness / readiness endpoint.

Always available so orchestration layers (Render) can poll it without business
logic being present.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.utils.config import get_settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    """Return service liveness and version information."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
    }
