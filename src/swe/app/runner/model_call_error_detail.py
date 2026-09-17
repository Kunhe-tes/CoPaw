# -*- coding: utf-8 -*-
"""User-visible model-call failure detail extraction."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from agentscope_runtime.engine.schemas.exception import AppBaseException

MODEL_CALL_FAILED_CODE = "model_call_failed"
MODEL_CALL_FAILED_MESSAGES_STATE_KEY = "model_call_failed_messages"
MAX_MODEL_CALL_ERROR_DETAIL_BYTES = 8 * 1024
TRUNCATION_MARKER = "\n\n[... truncated model-call error detail ...]\n\n"


class ModelCallFailureKind(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    CONNECTION = "connection"
    PROVIDER_STATUS = "provider_status"
    EMPTY_MODEL_OUTPUT = "empty_model_output"
    UNKNOWN_MODEL_CALL = "unknown_model_call"


@dataclass(frozen=True)
class ModelCallFailureDetail:
    code: str
    kind: ModelCallFailureKind
    message: str
    provider_status: int | None = None
    truncated: bool = False

    def as_error(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


class ModelCallFailedException(AppBaseException):
    """Runtime exception carrying a user-visible model-call failure detail."""

    def __init__(self, detail: ModelCallFailureDetail):
        super().__init__(
            status=422,
            code=detail.code,
            message=detail.message,
            details={
                "kind": detail.kind.value,
                "provider_status": detail.provider_status,
                "truncated": detail.truncated,
            },
        )
        self.detail = detail


_RATE_LIMIT_STATUS_CODES = {429, 432, 433, 529}
_PROVIDER_STATUS_CODES = {
    400,
    401,
    403,
    404,
    408,
    409,
    422,
    500,
    502,
    503,
    504,
}
_CONNECTION_TYPES: tuple[type[BaseException], ...] = (
    ConnectionError,
    ConnectionResetError,
    BrokenPipeError,
)
try:
    import httpx

    _CONNECTION_TYPES = (
        *_CONNECTION_TYPES,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
    )
    _TIMEOUT_TYPES: tuple[type[BaseException], ...] = (
        TimeoutError,
        asyncio.TimeoutError,
        httpx.TimeoutException,
    )
except ImportError:
    _TIMEOUT_TYPES = (TimeoutError, asyncio.TimeoutError)

_RATE_LIMIT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"rate[ -]?limit",
        r"too many requests",
        r"quota exceeded",
        r"throttl",
        r"token.*limit",
        r"token.*上限",
        r"输入.*已达.*上限",
    )
]
_MODEL_MARKER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bmodel\b",
        r"\bprovider\b",
        r"\bllm\b",
        r"\bopenai\b",
        r"\banthropic\b",
        r"\bchat.?completion\b",
        r"\bcompletion\b",
        r"empty model output",
    )
]
_REDACTION_PATTERNS = [
    re.compile(
        r"(?i)(authorization\s*:\s*(?:bearer\s+)?)([^\s,;]+)",
    ),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._~+/=-]{8,})"),
    re.compile(r"(?i)(cookie\s*:\s*)([^\n\r]+)"),
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|"
        r"password|session[_-]?token)\b\s*[:=]\s*([\"']?)[^\"'\s,;]+(\2)",
    ),
]


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = getattr(current, "__cause__", None) or getattr(
            current,
            "__context__",
            None,
        )
    return chain


def _status_code(exc: BaseException) -> int | None:
    value = getattr(exc, "status_code", None)
    if value is None:
        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _body_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for path in (
            ("error", "message"),
            ("message",),
            ("error_description",),
            ("detail",),
        ):
            cursor: Any = value
            for key in path:
                if not isinstance(cursor, dict):
                    cursor = None
                    break
                cursor = cursor.get(key)
            if isinstance(cursor, str) and cursor:
                return cursor
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _response_to_text(response: Any) -> str:
    if response is None:
        return ""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text
    content = getattr(response, "content", None)
    body_text = _body_to_text(content)
    if body_text:
        return body_text
    json_method = getattr(response, "json", None)
    if callable(json_method):
        try:
            return _body_to_text(json_method())
        except Exception:
            return ""
    return ""


def _detail_text(exc: BaseException) -> str:
    candidates = [
        getattr(exc, "body", None),
        getattr(exc, "response_body", None),
        getattr(exc, "message", None),
        _response_to_text(getattr(exc, "response", None)),
        str(exc),
    ]
    for candidate in candidates:
        text = _body_to_text(candidate).strip()
        if text:
            return text
    return exc.__class__.__name__


def _has_rate_limit_marker(text: str) -> bool:
    return any(pattern.search(text) for pattern in _RATE_LIMIT_PATTERNS)


def _has_model_marker(exc: BaseException, text: str) -> bool:
    class_path = f"{exc.__class__.__module__}.{exc.__class__.__name__}"
    haystack = f"{class_path} {text}"
    return any(pattern.search(haystack) for pattern in _MODEL_MARKER_PATTERNS)


def _classify(
    exc: BaseException,
    *,
    chain_has_model_marker: bool,
) -> ModelCallFailureKind | None:
    status = _status_code(exc)
    text = _detail_text(exc)
    lowered_text = text.lower()
    class_name = exc.__class__.__name__.lower()
    has_model_marker = _has_model_marker(exc, text)

    if "empty model output" in lowered_text or (
        "emptymodeloutput" in class_name
    ):
        return ModelCallFailureKind.EMPTY_MODEL_OUTPUT
    if not chain_has_model_marker:
        return None
    if isinstance(exc, _TIMEOUT_TYPES) or "timed out" in lowered_text:
        return ModelCallFailureKind.TIMEOUT
    if isinstance(exc, _CONNECTION_TYPES):
        return ModelCallFailureKind.CONNECTION
    if status in _RATE_LIMIT_STATUS_CODES:
        return ModelCallFailureKind.RATE_LIMIT
    if status is not None and (
        status >= 400 or status in _PROVIDER_STATUS_CODES
    ):
        return ModelCallFailureKind.PROVIDER_STATUS
    if _has_rate_limit_marker(text):
        return ModelCallFailureKind.RATE_LIMIT
    if has_model_marker:
        return ModelCallFailureKind.UNKNOWN_MODEL_CALL
    return None


def _recognizable_failures(
    exc: BaseException,
) -> list[tuple[BaseException, ModelCallFailureKind]]:
    failures: list[tuple[BaseException, ModelCallFailureKind]] = []
    chain = _exception_chain(exc)
    chain_has_model_marker = any(
        _has_model_marker(item, _detail_text(item)) for item in chain
    )
    for item in chain:
        kind = _classify(
            item,
            chain_has_model_marker=chain_has_model_marker,
        )
        if kind is not None:
            failures.append((item, kind))
    return failures


def _summary_for_kind(
    kind: ModelCallFailureKind,
    provider_status: int | None = None,
) -> str:
    if kind == ModelCallFailureKind.TIMEOUT:
        return "The model call timed out after retries were exhausted."
    if kind == ModelCallFailureKind.RATE_LIMIT:
        return "The model provider rate-limited this request."
    if kind == ModelCallFailureKind.CONNECTION:
        return "The model provider connection failed."
    if kind == ModelCallFailureKind.PROVIDER_STATUS:
        status = f" ({provider_status})" if provider_status is not None else ""
        return f"The model provider returned an error status{status}."
    if kind == ModelCallFailureKind.EMPTY_MODEL_OUTPUT:
        return "The model returned Empty Model Output after retry exhaustion."
    return "The model call failed before it returned usable output."


def redact_sensitive_fragments(text: str) -> str:
    redacted = text
    for pattern in _REDACTION_PATTERNS:
        if pattern.pattern.startswith("(?i)\\b"):
            redacted = pattern.sub(r"\1=[REDACTED]", redacted)
        else:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def truncate_detail(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_MODEL_CALL_ERROR_DETAIL_BYTES:
        return text, False

    marker = TRUNCATION_MARKER.encode("utf-8")
    remaining = MAX_MODEL_CALL_ERROR_DETAIL_BYTES - len(marker)
    if remaining <= 0:
        return (
            TRUNCATION_MARKER[:MAX_MODEL_CALL_ERROR_DETAIL_BYTES].decode(
                "utf-8",
                errors="ignore",
            ),
            True,
        )

    head_len = remaining // 2
    tail_len = remaining - head_len
    head = encoded[:head_len].decode("utf-8", errors="ignore")
    tail = encoded[-tail_len:].decode("utf-8", errors="ignore")
    return f"{head}{TRUNCATION_MARKER}{tail}", True


def _build_detail(
    *,
    kind: ModelCallFailureKind,
    detail_text: str,
    provider_status: int | None = None,
) -> ModelCallFailureDetail:
    safe_detail = redact_sensitive_fragments(detail_text.strip())
    summary = _summary_for_kind(kind, provider_status)
    message, truncated = truncate_detail(f"{summary}\n\n{safe_detail}")
    return ModelCallFailureDetail(
        code=MODEL_CALL_FAILED_CODE,
        kind=kind,
        message=message,
        provider_status=provider_status,
        truncated=truncated,
    )


def build_empty_model_output_detail(
    diagnostic_text: str | None = None,
) -> ModelCallFailureDetail:
    return _build_detail(
        kind=ModelCallFailureKind.EMPTY_MODEL_OUTPUT,
        detail_text=diagnostic_text
        or "Empty Model Output after the configured retry was exhausted.",
    )


def extract_model_call_failure_detail(
    exc: BaseException,
) -> ModelCallFailureDetail | None:
    failures = _recognizable_failures(exc)
    if not failures:
        return None

    selected, kind = failures[-1]
    return _build_detail(
        kind=kind,
        detail_text=_detail_text(selected),
        provider_status=_status_code(selected),
    )
