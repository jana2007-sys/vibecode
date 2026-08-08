"""Domain exceptions and their HTTP mapping.

Routes raise domain errors; middleware converts them into HTTP responses.
Keeping errors in one module gives a single, testable mapping table.
"""

from __future__ import annotations

from typing import Any


class InterVueError(Exception):
    """Base class for all domain-specific errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(InterVueError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    code = "not_found"


class ValidationError(InterVueError):
    """Raised when business-rule validation fails."""

    status_code = 422
    code = "validation_error"


class StateTransitionError(ValidationError):
    """Raised when an illegal interview state transition is attempted."""

    code = "invalid_state_transition"


class LLMUnavailableError(InterVueError):
    """Raised when the LLM service is required but not configured/enabled."""

    status_code = 503
    code = "llm_unavailable"


class LLMError(InterVueError):
    """Raised when an LLM call fails at runtime (network, API, empty response)."""

    status_code = 502
    code = "llm_error"
