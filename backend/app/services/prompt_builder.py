"""Prompt construction (placeholder).

Will assemble validated prompt payloads from the static templates in
``app/prompts/templates`` plus dynamic context (session, question, transcript).
Until Gemini integration is enabled this service has no business logic.
"""

from __future__ import annotations

from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger(__name__)


class PromptBuilder:
    """Builds prompt payloads for LLM calls."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        #: Default to backend/app/prompts/templates unless overridden.
        self._templates_dir = templates_dir or (
            Path(__file__).resolve().parent.parent / "prompts" / "templates"
        )

    def load_template(self, template_name: str) -> str:
        """Read a named template file from the templates directory.

        Placeholder: will be used by prompt-building methods below.
        """
        raise NotImplementedError("Prompt building will be implemented later.")

    def build_question_prompt(self, session_id: str, question: str) -> str:
        """Compose the prompt for generating the next interviewer question.

        Placeholder: no prompt construction yet.
        """
        raise NotImplementedError("Prompt building will be implemented later.")

    def build_evaluation_prompt(self, session_id: str, answer: str) -> str:
        """Compose the prompt for scoring a candidate answer.

        Placeholder: no prompt construction yet.
        """
        raise NotImplementedError("Prompt building will be implemented later.")

    def build_feedback_prompt(self, session_id: str) -> str:
        """Compose the prompt for generating the final report narrative.

        Placeholder: no prompt construction yet.
        """
        raise NotImplementedError("Prompt building will be implemented later.")
