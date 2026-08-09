"""Gemini API client backed by the current official Google GenAI SDK.

Wraps ``google-genai`` (NOT the legacy ``google-generativeai``) behind a stable
interface so that swapping the LLM provider never touches interview logic.

The service is inert until ``GEMINI_ENABLED=true`` and ``GEMINI_API_KEY`` are
configured; the ``enabled`` property is the single gate. While disabled, no SDK
client is created and every call raises ``LLMUnavailableError``, so the
deterministic interview implementation never depends on Gemini merely to boot.
"""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.utils.config import Settings, get_settings
from app.utils.errors import LLMError, LLMUnavailableError, ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Per-request timeout in milliseconds (google-genai uses milliseconds).
DEFAULT_TIMEOUT_MS = 60_000

#: Minimal SDK-native retry (tenacity-backed) for transient/API failures.
RETRY_ATTEMPTS = 2
RETRY_STATUS_CODES = [429, 500, 502, 503]


class GeminiService:
    """Wraps the Gemini API. Inert until explicitly enabled."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: genai.Client | None = None

    @property
    def enabled(self) -> bool:
        """Return True only when Gemini is configured and switched on."""
        return bool(
            self._settings.gemini_enabled and self._settings.gemini_api_key
        )

    def _require_enabled(self) -> None:
        """Guard every LLM call with a clear error when disabled."""
        if not self.enabled:
            raise LLMUnavailableError(
                "Gemini integration is not enabled. Set GEMINI_ENABLED=true "
                "and provide GEMINI_API_KEY in the environment."
            )

    def _http_options(self) -> genai_types.HttpOptions:
        """Sensible timeout + minimal retry, without aggressive retry loops."""
        return genai_types.HttpOptions(
            timeout=DEFAULT_TIMEOUT_MS,
            retry_options=genai_types.HttpRetryOptions(
                attempts=RETRY_ATTEMPTS,
                http_status_codes=RETRY_STATUS_CODES,
            ),
        )

    def _get_client(self) -> genai.Client:
        """Create (once) the SDK client bound to the configured API key."""
        self._require_enabled()
        if self._client is None:
            self._client = genai.Client(
                api_key=self._settings.gemini_api_key,
                http_options=self._http_options(),
            )
        return self._client

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt to Gemini and return generated text.

        Raises ``LLMUnavailableError`` when disabled, ``LLMError`` on API
        failures or empty responses, and ``ValidationError`` on malformed
        output. Never logs the API key or request content.
        """
        response = self._generate(prompt, mime_type=None, schema=None, **kwargs)
        text = response.text
        if not text or not text.strip():
            raise LLMError(
                "Gemini returned an empty response.",
                details={"method": "generate_text"},
            )
        return text.strip()

    def generate_json(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        """Request structured JSON from Gemini and return it as a Python dict.

        Uses the SDK's JSON response capability (``response_mime_type`` +
        ``response_schema``), parses the response text, and validates the
        structure against ``schema`` before returning. Pass ``model=`` to target
        a specific model (defaults to the configured ``GEMINI_MODEL``). Raises
        ``ValidationError`` when the response is malformed or does not satisfy
        the expected structure, ``LLMError`` on API/empty failures, and
        ``LLMUnavailableError`` when disabled.
        """
        response = self._generate(
            prompt, mime_type="application/json", schema=schema, **kwargs
        )
        raw = (response.text or "").strip()
        if not raw:
            raise LLMError(
                "Gemini returned an empty response.",
                details={"method": "generate_json"},
            )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Gemini returned malformed JSON.",
                details={"error": str(exc)},
            ) from exc
        if not isinstance(payload, dict):
            raise ValidationError(
                "Gemini JSON response must be an object.",
                details={"type": type(payload).__name__},
            )
        self._validate(payload, schema, path="$")
        return payload

    def _generate(
        self,
        prompt: str,
        *,
        mime_type: str | None,
        schema: dict | None,
        **kwargs: Any,
    ) -> Any:
        """Run the SDK call, mapping every failure onto the error hierarchy.

        ``model`` (optional keyword) selects a specific model; otherwise the
        configured ``GEMINI_MODEL`` is used.
        """
        model = kwargs.pop("model", None)
        try:
            client = self._get_client()
            config = self._build_config(mime_type=mime_type, schema=schema, **kwargs)
            return client.models.generate_content(
                model=model or self._settings.gemini_model,
                contents=prompt,
                config=config,
            )
        except (LLMUnavailableError, ValidationError):
            raise
        except Exception as exc:  # noqa: BLE001 - boundary conversion
            # Log only the error category; never the key, prompt, or response.
            logger.error("Gemini API call failed: %s", type(exc).__name__)
            raise LLMError(
                "Gemini API call failed.",
                details={"error_type": type(exc).__name__},
            ) from exc

    @staticmethod
    def _build_config(
        *,
        mime_type: str | None,
        schema: dict | None,
        **kwargs: Any,
    ) -> genai_types.GenerateContentConfig:
        """Assemble the generation config, forwarding only known knobs."""
        options: dict[str, Any] = {}
        for key in (
            "max_output_tokens",
            "temperature",
            "top_p",
            "top_k",
            "stop_sequences",
            "seed",
        ):
            if key in kwargs:
                options[key] = kwargs[key]
        if mime_type is not None:
            options["response_mime_type"] = mime_type
        if schema is not None:
            options["response_schema"] = schema
        return genai_types.GenerateContentConfig(**options)

    def _validate(self, data: Any, schema: Any, *, path: str) -> None:
        """Recursively validate ``data`` against a JSON-schema style dict."""
        if not isinstance(schema, dict):
            return  # no schema to check against
        schema_type = (schema.get("type") or "ANY").upper()
        if schema_type == "ANY":
            return
        if schema_type == "OBJECT":
            self._validate_object(data, schema, path)
        elif schema_type == "ARRAY":
            self._validate_array(data, schema, path)
        elif schema_type == "STRING" and not isinstance(data, str):
            raise ValidationError(
                f"Gemini JSON response field '{path}' must be a string.",
                details={"path": path, "actual": type(data).__name__},
            )
        elif schema_type == "INTEGER" and (
            isinstance(data, bool) or not isinstance(data, int)
        ):
            raise ValidationError(
                f"Gemini JSON response field '{path}' must be an integer.",
                details={"path": path, "actual": type(data).__name__},
            )
        elif schema_type == "NUMBER" and (
            isinstance(data, bool) or not isinstance(data, (int, float))
        ):
            raise ValidationError(
                f"Gemini JSON response field '{path}' must be a number.",
                details={"path": path, "actual": type(data).__name__},
            )
        elif schema_type == "BOOLEAN" and not isinstance(data, bool):
            raise ValidationError(
                f"Gemini JSON response field '{path}' must be a boolean.",
                details={"path": path, "actual": type(data).__name__},
            )
        elif schema_type == "NULL" and data is not None:
            raise ValidationError(
                f"Gemini JSON response field '{path}' must be null.",
                details={"path": path, "actual": type(data).__name__},
            )
        elif schema_type == "ENUM" and data not in (schema.get("enum") or []):
            raise ValidationError(
                f"Gemini JSON response field '{path}' is not an allowed value.",
                details={"path": path, "allowed": schema.get("enum")},
            )

    def _validate_object(self, data: Any, schema: dict, path: str) -> None:
        if not isinstance(data, dict):
            raise ValidationError(
                f"Gemini JSON response field '{path}' must be an object.",
                details={"path": path, "actual": type(data).__name__},
            )
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in data:
                raise ValidationError(
                    f"Gemini JSON response is missing required property "
                    f"'{name}' at '{path}'.",
                    details={"path": f"{path}.{name}"},
                )
        for name, value in data.items():
            if name in properties:
                self._validate(value, properties[name], path=f"{path}.{name}")

    def _validate_array(self, data: Any, schema: dict, path: str) -> None:
        if not isinstance(data, list):
            raise ValidationError(
                f"Gemini JSON response field '{path}' must be an array.",
                details={"path": path, "actual": type(data).__name__},
            )
        items = schema.get("items") or {}
        for index, item in enumerate(data):
            self._validate(item, items, path=f"{path}[{index}]")
