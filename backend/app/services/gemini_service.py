"""Gemini API client — PLACEHOLDER ONLY.

Integration is intentionally NOT implemented. This class defines the stable
interface the rest of the system will call once ``GEMINI_ENABLED=true``.

Expected future methods (kept as a contract, not implemented):
  - ``generate_text(prompt, **params) -> str``
  - ``generate_json(prompt, schema, **params) -> dict``

All collaborators depend on this interface, so swapping the LLM provider (or
enabling Gemini) never touches interview logic.
"""

from __future__ import annotations

from typing import Any

from app.utils.config import Settings, get_settings
from app.utils.errors import LLMUnavailableError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class GeminiService:
    """Wraps the Gemini API. Inert until explicitly enabled."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        """Return True only when Gemini is configured and switched on."""
        return bool(
            self._settings.gemini_enabled and self._settings.gemini_api_key
        )

    def _require_enabled(self) -> None:
        """Guard every future LLM call with a clear error when disabled."""
        if not self.enabled:
            raise LLMUnavailableError(
                "Gemini integration is not enabled. Set GEMINI_ENABLED=true "
                "and provide GEMINI_API_KEY in the environment."
            )

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt to Gemini and return generated text.

        Placeholder: raises until integration is implemented.
        """
        self._require_enabled()
        raise NotImplementedError("Gemini integration will be implemented later.")

    def generate_json(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        """Send a prompt and request a JSON response matching ``schema``.

        Placeholder: raises until integration is implemented.
        """
        self._require_enabled()
        raise NotImplementedError("Gemini integration will be implemented later.")
