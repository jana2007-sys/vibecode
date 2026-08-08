"""Focused tests for GeminiService (Google GenAI SDK integration).

The SDK client is fully mocked — no real Gemini API call is ever made. The
service reads only ``response.text`` and returns primitives, so a lightweight
stand-in response object is sufficient.
"""

from __future__ import annotations

import json
import logging
from unittest import mock

import pytest

import app.services.gemini_service as gemini_module
from app.services.gemini_service import GeminiService
from app.utils.config import Settings
from app.utils.errors import LLMError, LLMUnavailableError, ValidationError

API_KEY = "sk-test-gemini-12345-not-a-real-key"

OBJECT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING"},
        "score": {"type": "NUMBER"},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["name", "score"],
}


def _settings(**overrides) -> Settings:
    base = {
        "gemini_enabled": True,
        "gemini_api_key": API_KEY,
        "gemini_model": "gemini-2.0-flash",
    }
    base.update(overrides)
    return Settings(**base)


class _Response:
    """Minimal stand-in for the SDK response; only ``.text`` is read."""

    def __init__(self, text: str | None) -> None:
        self.text = text


def _install_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response: object = _Response("hello"),
    error: Exception | None = None,
) -> tuple[mock.MagicMock, mock.MagicMock, mock.MagicMock]:
    """Swap ``google.genai.Client`` for a fake; return the fakes for asserts."""
    models = mock.MagicMock()
    models.generate_content.return_value = response
    models.generate_content.side_effect = error
    client = mock.MagicMock()
    client.models = models
    fake_client_cls = mock.MagicMock(return_value=client)
    monkeypatch.setattr(gemini_module.genai, "Client", fake_client_cls)
    return fake_client_cls, client, models


# --- Configuration / gating --------------------------------------------------


class TestConfiguration:
    def test_disabled_gemini_raises_unavailable_and_never_creates_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_client_cls, _, _ = _install_client(monkeypatch)
        service = GeminiService(settings=_settings(gemini_enabled=False))
        assert service.enabled is False
        with pytest.raises(LLMUnavailableError):
            service.generate_text("hello")
        with pytest.raises(LLMUnavailableError):
            service.generate_json("hello", OBJECT_SCHEMA)
        fake_client_cls.assert_not_called()

    def test_missing_api_key_raises_unavailable(self) -> None:
        service = GeminiService(settings=_settings(gemini_api_key=""))
        assert service.enabled is False
        with pytest.raises(LLMUnavailableError, match="GEMINI_API_KEY"):
            service.generate_text("hello")
        with pytest.raises(LLMUnavailableError, match="GEMINI_API_KEY"):
            service.generate_json("hello", OBJECT_SCHEMA)

    def test_enabled_configuration(self) -> None:
        assert GeminiService(settings=_settings()).enabled is True
        assert (
            GeminiService(settings=_settings(gemini_enabled=True, gemini_api_key="")).enabled
            is False
        )
        assert (
            GeminiService(settings=_settings(gemini_enabled=False, gemini_api_key=API_KEY)).enabled
            is False
        )


# --- generate_text -----------------------------------------------------------


class TestGenerateText:
    def test_success_returns_stripped_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_client_cls, _, models = _install_client(
            monkeypatch, response=_Response("  Hello there  ")
        )
        service = GeminiService(settings=_settings())
        assert service.generate_text("Say hi") == "Hello there"

        fake_client_cls.assert_called_once()
        assert fake_client_cls.call_args.kwargs["api_key"] == API_KEY
        call = models.generate_content.call_args
        assert call.kwargs["model"] == "gemini-2.0-flash"
        assert call.kwargs["contents"] == "Say hi"
        assert call.kwargs["config"] is not None

    def test_unknown_kwargs_are_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_client(monkeypatch, response=_Response("ok"))
        service = GeminiService(settings=_settings())
        assert service.generate_text("hi", bogus_option=123) == "ok"

    def test_api_failure_raises_llm_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_client(monkeypatch, error=RuntimeError("connection reset"))
        service = GeminiService(settings=_settings())
        with pytest.raises(LLMError, match="Gemini API call failed"):
            service.generate_text("hello")

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_empty_response_raises_llm_error(
        self, monkeypatch: pytest.MonkeyPatch, text: str | None
    ) -> None:
        _install_client(monkeypatch, response=_Response(text))
        service = GeminiService(settings=_settings())
        with pytest.raises(LLMError, match="empty response"):
            service.generate_text("hello")


# --- generate_json -----------------------------------------------------------


class TestGenerateJson:
    def test_success_returns_parsed_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {"name": "Alex", "score": 9.5, "tags": ["solid", "clear"]}
        _, _, models = _install_client(
            monkeypatch, response=_Response(json.dumps(payload))
        )
        service = GeminiService(settings=_settings())
        assert service.generate_json("evaluate", OBJECT_SCHEMA) == payload

        config = models.generate_content.call_args.kwargs["config"]
        assert config.response_mime_type == "application/json"
        assert config.response_schema == OBJECT_SCHEMA

    def test_malformed_json_raises_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_client(monkeypatch, response=_Response("{not valid json"))
        service = GeminiService(settings=_settings())
        with pytest.raises(ValidationError, match="malformed JSON"):
            service.generate_json("evaluate", OBJECT_SCHEMA)

    def test_non_object_top_level_raises_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_client(monkeypatch, response=_Response("[1, 2, 3]"))
        service = GeminiService(settings=_settings())
        with pytest.raises(ValidationError, match="must be an object"):
            service.generate_json("evaluate", OBJECT_SCHEMA)

    def test_invalid_primitive_type_raises_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_client(monkeypatch, response=_Response(json.dumps({"name": 123, "score": 9.5})))
        service = GeminiService(settings=_settings())
        with pytest.raises(ValidationError) as exc_info:
            service.generate_json("evaluate", OBJECT_SCHEMA)
        assert (
            exc_info.value.message
            == "Gemini JSON response field '$.name' must be a string."
        )

    def test_missing_required_property_raises_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_client(monkeypatch, response=_Response(json.dumps({"name": "Alex"})))
        service = GeminiService(settings=_settings())
        with pytest.raises(ValidationError, match="missing required property 'score'"):
            service.generate_json("evaluate", OBJECT_SCHEMA)

    def test_nested_structure_is_validated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        schema = {
            "type": "OBJECT",
            "properties": {
                "items": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {"id": {"type": "STRING"}, "ok": {"type": "BOOLEAN"}},
                        "required": ["id"],
                    },
                }
            },
            "required": ["items"],
        }
        _install_client(
            monkeypatch,
            response=_Response(json.dumps({"items": [{"id": "a", "ok": True}]})),
        )
        service = GeminiService(settings=_settings())
        assert service.generate_json("go", schema) == {"items": [{"id": "a", "ok": True}]}

    def test_nested_missing_required_property_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        schema = {
            "type": "OBJECT",
            "properties": {
                "items": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {"id": {"type": "STRING"}},
                        "required": ["id"],
                    },
                }
            },
            "required": ["items"],
        }
        _install_client(
            monkeypatch,
            response=_Response(json.dumps({"items": [{"ok": True}]})),
        )
        service = GeminiService(settings=_settings())
        with pytest.raises(ValidationError, match="missing required property 'id'"):
            service.generate_json("go", schema)

    def test_api_failure_raises_llm_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_client(monkeypatch, error=RuntimeError("rate limited"))
        service = GeminiService(settings=_settings())
        with pytest.raises(LLMError, match="Gemini API call failed"):
            service.generate_json("evaluate", OBJECT_SCHEMA)


# --- Safety ------------------------------------------------------------------


class TestSafety:
    def test_api_key_is_never_logged(self, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        leaky_error = RuntimeError(f"authentication failed for key {API_KEY}")
        _install_client(monkeypatch, error=leaky_error)
        service = GeminiService(settings=_settings())
        with caplog.at_level(logging.ERROR):
            with pytest.raises(LLMError):
                service.generate_text("hello")
        assert API_KEY not in caplog.text

    def test_error_payload_does_not_include_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_client(monkeypatch, error=RuntimeError(f"boom with {API_KEY}"))
        service = GeminiService(settings=_settings())
        with pytest.raises(LLMError) as exc_info:
            service.generate_text("hello")
        message = exc_info.value.message + str(exc_info.value.details)
        assert API_KEY not in message
