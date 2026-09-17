# -*- coding: utf-8 -*-
"""Runtime invocation claim construction and transport mapping."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Callable, Iterator, Mapping, MutableMapping

from swe.config.context import (
    get_current_scope_id,
    get_current_source_id,
    get_current_tenant_id,
    resolve_runtime_tenant_id,
)

_RUNTIME_CLAIMS_CONTEXT: ContextVar["RuntimeInvocationClaims | None"] = (
    ContextVar(
        "runtime_invocation_claims",
        default=None,
    )
)

RUNTIME_CLAIM_ENV_KEYS = frozenset(
    {
        "SWE_TENANT_ID",
        "SWE_SOURCE_ID",
        "SWE_RUNTIME_SCOPE_ID",
        "SWE_SESSION_ID",
        "SWE_CHAT_ID",
        "SWE_TRACE_ID",
    },
)

_CANONICAL_HEADER_NAMES = {
    "tenant_id": "x-swe-tenant-id",
    "source_id": "x-swe-source-id",
    "runtime_scope_id": "x-swe-runtime-scope-id",
    "session_id": "x-swe-session-id",
    "chat_id": "x-swe-chat-id",
    "trace_id": "x-swe-trace-id",
}
_ALIAS_HEADER_NAMES = {
    "tenant_id": "tenantid",
    "source_id": "sourceid",
    "session_id": "sessionid",
    "chat_id": "chatid",
    "trace_id": "traceid",
}
RUNTIME_CLAIM_HEADER_KEYS = frozenset(
    {
        *(_CANONICAL_HEADER_NAMES.values()),
        *(_ALIAS_HEADER_NAMES.values()),
    },
)


@dataclass(frozen=True)
class RuntimeInvocationClaims:
    """Runtime claims propagated to trusted invocation boundaries."""

    tenant_id: str | None = None
    source_id: str | None = None
    runtime_scope_id: str | None = None
    session_id: str | None = None
    chat_id: str | None = None
    trace_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "tenant_id": self.tenant_id,
                "source_id": self.source_id,
                "runtime_scope_id": self.runtime_scope_id,
                "session_id": self.session_id,
                "chat_id": self.chat_id,
                "trace_id": self.trace_id,
            }.items()
            if value
        }


def _coerce(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _resolve_claim_value(
    explicit_value: object | None,
    current: RuntimeInvocationClaims | None,
    claim_name: str,
    default: Callable[[], object | None] | None = None,
) -> str | None:
    if explicit_value is not None:
        return _coerce(explicit_value)
    if current is not None:
        current_value = getattr(current, claim_name)
        if current_value is not None:
            return _coerce(current_value)
    if default is None:
        return None
    return _coerce(default())


def build_runtime_invocation_claims(
    *,
    tenant_id: str | None = None,
    source_id: str | None = None,
    runtime_scope_id: str | None = None,
    session_id: str | None = None,
    chat_id: str | None = None,
    trace_id: str | None = None,
) -> RuntimeInvocationClaims:
    """Build invocation claims from explicit values, context, and tenant scope."""
    current = _RUNTIME_CLAIMS_CONTEXT.get()
    effective_tenant_id = _resolve_claim_value(
        tenant_id,
        current,
        "tenant_id",
        get_current_tenant_id,
    )
    effective_source_id = _resolve_claim_value(
        source_id,
        current,
        "source_id",
        get_current_source_id,
    )
    effective_runtime_scope_id = _resolve_claim_value(
        runtime_scope_id,
        current,
        "runtime_scope_id",
        lambda: get_current_scope_id()
        or resolve_runtime_tenant_id(
            effective_tenant_id,
            effective_source_id,
        ),
    )
    effective_session_id = _resolve_claim_value(
        session_id,
        current,
        "session_id",
    )
    effective_chat_id = _resolve_claim_value(
        chat_id,
        current,
        "chat_id",
    )
    effective_trace_id = _resolve_claim_value(
        trace_id,
        current,
        "trace_id",
    )
    return RuntimeInvocationClaims(
        tenant_id=effective_tenant_id,
        source_id=effective_source_id,
        runtime_scope_id=effective_runtime_scope_id,
        session_id=effective_session_id,
        chat_id=effective_chat_id,
        trace_id=effective_trace_id,
    )


@contextmanager
def runtime_invocation_claims_context(
    *,
    tenant_id: str | None = None,
    source_id: str | None = None,
    runtime_scope_id: str | None = None,
    session_id: str | None = None,
    chat_id: str | None = None,
    trace_id: str | None = None,
) -> Iterator[RuntimeInvocationClaims]:
    """Temporarily set backend-local runtime invocation claims."""
    claims = build_runtime_invocation_claims(
        tenant_id=tenant_id,
        source_id=source_id,
        runtime_scope_id=runtime_scope_id,
        session_id=session_id,
        chat_id=chat_id,
        trace_id=trace_id,
    )
    token: Token = _RUNTIME_CLAIMS_CONTEXT.set(claims)
    try:
        yield claims
    finally:
        _RUNTIME_CLAIMS_CONTEXT.reset(token)


def apply_runtime_claim_env(
    env: Mapping[str, str] | MutableMapping[str, str],
    *,
    tenant_id: str | None = None,
    source_id: str | None = None,
    runtime_scope_id: str | None = None,
    session_id: str | None = None,
    chat_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, str]:
    """Return env with runtime-owned claim keys removed and current claims set."""
    result = {
        str(key): str(value)
        for key, value in env.items()
        if str(key) not in RUNTIME_CLAIM_ENV_KEYS
    }
    claims = build_runtime_invocation_claims(
        tenant_id=tenant_id,
        source_id=source_id,
        runtime_scope_id=runtime_scope_id,
        session_id=session_id,
        chat_id=chat_id,
        trace_id=trace_id,
    )
    mapping = {
        "SWE_TENANT_ID": claims.tenant_id,
        "SWE_SOURCE_ID": claims.source_id,
        "SWE_RUNTIME_SCOPE_ID": claims.runtime_scope_id,
        "SWE_SESSION_ID": claims.session_id,
        "SWE_CHAT_ID": claims.chat_id,
        "SWE_TRACE_ID": claims.trace_id,
    }
    result.update({key: value for key, value in mapping.items() if value})
    return result


def build_runtime_claim_headers(
    headers: Mapping[str, str] | None = None,
    *,
    include_aliases: bool = False,
    tenant_id: str | None = None,
    source_id: str | None = None,
    runtime_scope_id: str | None = None,
    session_id: str | None = None,
    chat_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, str]:
    """Return headers with runtime-owned claim names removed and claims set."""
    result = {
        str(key): str(value)
        for key, value in (headers or {}).items()
        if str(key).lower() not in RUNTIME_CLAIM_HEADER_KEYS
    }
    claims = build_runtime_invocation_claims(
        tenant_id=tenant_id,
        source_id=source_id,
        runtime_scope_id=runtime_scope_id,
        session_id=session_id,
        chat_id=chat_id,
        trace_id=trace_id,
    )
    values = claims.as_dict()
    for claim_key, header_name in _CANONICAL_HEADER_NAMES.items():
        value = values.get(claim_key)
        if value:
            result[header_name] = value
    if include_aliases:
        for claim_key, header_name in _ALIAS_HEADER_NAMES.items():
            value = values.get(claim_key)
            if value:
                result[header_name] = value
    return result
