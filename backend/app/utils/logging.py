"""Centralized logging bootstrap.

Import and call ``configure_logging()`` once at application startup, then use
module-level ``logger = logging.getLogger(__name__)`` everywhere else.
"""

from __future__ import annotations

import logging
import sys

from app.utils.config import get_settings

_CONFIGURED = False


def configure_logging() -> None:
    """Configure root logging once. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = logging.DEBUG if settings.app_env == "development" else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with the app's logging config applied."""
    configure_logging()
    return logging.getLogger(name)
