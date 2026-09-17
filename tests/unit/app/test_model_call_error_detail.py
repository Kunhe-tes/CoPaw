# -*- coding: utf-8 -*-

import asyncio

from src.swe.app.runner.model_call_error_detail import (
    MODEL_CALL_FAILED_CODE,
    ModelCallFailureKind,
    build_empty_model_output_detail,
    extract_model_call_failure_detail,
)
from src.swe.providers.retry_chat_model import EmptyModelOutputError


class _ResponseText:
    text = "provider body says quota exceeded"


class _ResponseJson:
    def json(self):
        return {"error": {"message": "json provider diagnostic"}}


class _ToolResponseText:
    text = "tool API returned server error"


class _ProviderStatusError(Exception):
    __module__ = "provider.runtime"
    status_code = 500
    response = _ResponseText()


class _ProviderRateLimitError(Exception):
    __module__ = "provider.runtime"
    status_code = 429
    body = {"message": "Rate limit exceeded for project"}


class _ProviderMessageError(Exception):
    __module__ = "provider.runtime"
    message = "provider message field"


class _ToolStatusError(Exception):
    __module__ = "tool_runtime"
    status_code = 500
    response = _ToolResponseText()


class _ToolRateLimitError(Exception):
    __module__ = "tool_runtime"
    status_code = 429
    body = {"message": "too many requests from tool API"}


def test_classifies_timeout_rate_limit_connection_provider_and_unknown():
    timeout = extract_model_call_failure_detail(
        asyncio.TimeoutError("model provider timed out"),
    )
    rate_limit = extract_model_call_failure_detail(_ProviderRateLimitError())
    connection = extract_model_call_failure_detail(
        ConnectionResetError("model provider socket reset"),
    )
    provider = extract_model_call_failure_detail(_ProviderStatusError("bad"))
    unknown = extract_model_call_failure_detail(
        RuntimeError("model provider returned malformed chunks"),
    )

    assert timeout is not None
    assert timeout.code == MODEL_CALL_FAILED_CODE
    assert timeout.kind == ModelCallFailureKind.TIMEOUT
    assert "timed out" in timeout.message.lower()

    assert rate_limit is not None
    assert rate_limit.kind == ModelCallFailureKind.RATE_LIMIT
    assert "rate limit" in rate_limit.message.lower()

    assert connection is not None
    assert connection.kind == ModelCallFailureKind.CONNECTION

    assert provider is not None
    assert provider.kind == ModelCallFailureKind.PROVIDER_STATUS
    assert provider.provider_status == 500
    assert "provider body says quota exceeded" in provider.message

    assert unknown is not None
    assert unknown.kind == ModelCallFailureKind.UNKNOWN_MODEL_CALL


def test_ignores_unmarked_transport_and_status_failures():
    assert (
        extract_model_call_failure_detail(
            asyncio.TimeoutError("tool call timed out"),
        )
        is None
    )
    assert (
        extract_model_call_failure_detail(
            ConnectionResetError("tool socket reset"),
        )
        is None
    )
    assert (
        extract_model_call_failure_detail(
            _ToolStatusError("hook callback failed"),
        )
        is None
    )
    assert (
        extract_model_call_failure_detail(
            _ToolRateLimitError("tool API quota exceeded"),
        )
        is None
    )


def test_uses_chain_model_marker_for_specific_inner_failure():
    inner = asyncio.TimeoutError("timed out")
    outer = RuntimeError("model call failed")
    outer.__cause__ = inner

    detail = extract_model_call_failure_detail(outer)

    assert detail is not None
    assert detail.kind == ModelCallFailureKind.TIMEOUT


def test_uses_innermost_recognizable_failure_and_skips_plain_wrappers():
    inner = _ProviderMessageError("inner provider")
    middle = RuntimeError("middle generic wrapper")
    middle.__cause__ = inner
    outer = RuntimeError("outer generic wrapper")
    outer.__cause__ = middle

    detail = extract_model_call_failure_detail(outer)

    assert detail is not None
    assert detail.kind == ModelCallFailureKind.UNKNOWN_MODEL_CALL
    assert "provider message field" in detail.message
    assert "outer generic wrapper" not in detail.message


def test_extracts_response_json_body_and_chained_context():
    inner = Exception("outer text should not win")
    inner.status_code = 503
    inner.response = _ResponseJson()
    outer = RuntimeError("generic wrapper")
    outer.__context__ = inner

    detail = extract_model_call_failure_detail(outer)

    assert detail is not None
    assert detail.kind == ModelCallFailureKind.PROVIDER_STATUS
    assert detail.provider_status == 503
    assert "json provider diagnostic" in detail.message


def test_redacts_sensitive_fragments_before_detail_is_returned():
    exc = RuntimeError(
        "model call failed with Authorization: Bearer sk-live-abc123 "
        "cookie: session=secret-token api_key=abc123 secret='hidden'",
    )

    detail = extract_model_call_failure_detail(exc)

    assert detail is not None
    assert "sk-live-abc123" not in detail.message
    assert "secret-token" not in detail.message
    assert "api_key=abc123" not in detail.message
    assert "secret='hidden'" not in detail.message
    assert "[REDACTED]" in detail.message


def test_truncates_long_detail_to_8kb_with_beginning_and_end():
    long_text = "model call failed start-" + ("x" * 9000) + "-end"
    detail = extract_model_call_failure_detail(RuntimeError(long_text))

    assert detail is not None
    encoded = detail.message.encode("utf-8")
    assert len(encoded) <= 8192
    assert "start-" in detail.message
    assert "-end" in detail.message
    assert "[... truncated" in detail.message
    assert detail.truncated is True


def test_builds_empty_model_output_detail_without_provider_text():
    detail = build_empty_model_output_detail(
        "Empty Model Output after retry exhausted",
    )

    assert detail.code == MODEL_CALL_FAILED_CODE
    assert detail.kind == ModelCallFailureKind.EMPTY_MODEL_OUTPUT
    assert "empty model output" in detail.message.lower()
    assert "after retry exhausted" in detail.message.lower()


def test_classifies_provider_empty_model_output_error():
    detail = extract_model_call_failure_detail(
        EmptyModelOutputError(
            "LLM call returned empty model output after retry",
        ),
    )

    assert detail is not None
    assert detail.kind == ModelCallFailureKind.EMPTY_MODEL_OUTPUT
    assert "empty model output" in detail.message.lower()
