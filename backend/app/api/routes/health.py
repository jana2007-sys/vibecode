"""Liveness / readiness endpoint.

Always available so orchestration layers (Render) can poll it without business
logic being present. Includes a safe database connectivity check that never
leaks credentials or internal configuration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.database.connection import Database, get_database
from app.utils.config import get_settings

router = APIRouter()


@router.get("/health")
def health_check(db: Database = Depends(get_database)) -> dict:
    """Return service liveness, version info, and database connectivity."""
    settings = get_settings()
    payload: dict = {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
        "database": "ok",
    }
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
    except Exception:  # noqa: BLE001 - surface degraded state, not the error detail
        payload["status"] = "degraded"
        payload["database"] = "error"
    return payload
