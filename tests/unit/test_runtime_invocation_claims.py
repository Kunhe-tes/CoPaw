# -*- coding: utf-8 -*-
from __future__ import annotations

from swe.config.context import encode_scope_id, tenant_context


def test_runtime_invocation_claims_resolve_from_context_and_explicit_values():
    from swe.runtime_invocation_claims import build_runtime_invocation_claims

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        claims = build_runtime_invocation_claims(
            session_id="session-1",
            trace_id="trace-1",
        )

    assert claims.as_dict() == {
        "tenant_id": "tenant-a",
        "source_id": "source-a",
        "runtime_scope_id": encode_scope_id("tenant-a", "source-a"),
        "session_id": "session-1",
        "trace_id": "trace-1",
    }


def test_runtime_invocation_claims_context_supplies_nested_values():
    from swe.runtime_invocation_claims import (
        build_runtime_invocation_claims,
        runtime_invocation_claims_context,
    )

    with (
        tenant_context(tenant_id="tenant-a", source_id="source-a"),
        runtime_invocation_claims_context(
            session_id="session-1",
            trace_id="trace-1",
        ),
    ):
        claims = build_runtime_invocation_claims()

    assert claims.session_id == "session-1"
    assert claims.trace_id == "trace-1"
    assert claims.tenant_id == "tenant-a"
    assert claims.source_id == "source-a"


def test_runtime_claim_env_filters_and_overwrites_reserved_names():
    from swe.runtime_invocation_claims import apply_runtime_claim_env

    env = apply_runtime_claim_env(
        {
            "SWE_TENANT_ID": "fake-tenant",
            "SWE_SOURCE_ID": "fake-source",
            "APP_TOKEN": "ok",
        },
        tenant_id="tenant-a",
        source_id="source-a",
        runtime_scope_id="scope-a",
        session_id="session-1",
    )

    assert env == {
        "APP_TOKEN": "ok",
        "SWE_TENANT_ID": "tenant-a",
        "SWE_SOURCE_ID": "source-a",
        "SWE_RUNTIME_SCOPE_ID": "scope-a",
        "SWE_SESSION_ID": "session-1",
    }


def test_runtime_claim_headers_use_aliases_only_when_requested():
    from swe.runtime_invocation_claims import build_runtime_claim_headers

    base = {
        "X-Swe-Tenant-Id": "fake-tenant",
        "tenantid": "fake-tenant",
        "X-Static": "static",
    }
    canonical = build_runtime_claim_headers(
        base,
        tenant_id="tenant-a",
        source_id="source-a",
        trace_id="trace-1",
        include_aliases=False,
    )
    with_aliases = build_runtime_claim_headers(
        base,
        tenant_id="tenant-a",
        source_id="source-a",
        trace_id="trace-1",
        include_aliases=True,
    )

    assert canonical == {
        "X-Static": "static",
        "x-swe-tenant-id": "tenant-a",
        "x-swe-source-id": "source-a",
        "x-swe-runtime-scope-id": "dGVuYW50LWE.c291cmNlLWE",
        "x-swe-trace-id": "trace-1",
    }
    assert with_aliases == {
        "X-Static": "static",
        "x-swe-tenant-id": "tenant-a",
        "tenantid": "tenant-a",
        "x-swe-source-id": "source-a",
        "sourceid": "source-a",
        "x-swe-runtime-scope-id": "dGVuYW50LWE.c291cmNlLWE",
        "x-swe-trace-id": "trace-1",
        "traceid": "trace-1",
    }


def test_runtime_claim_env_replaces_static_chat_id():
    from swe.runtime_invocation_claims import apply_runtime_claim_env

    env = apply_runtime_claim_env(
        {"SWE_CHAT_ID": "untrusted", "APP_TOKEN": "ok"},
        chat_id="chat-uuid-1",
    )

    assert env == {
        "APP_TOKEN": "ok",
        "SWE_CHAT_ID": "chat-uuid-1",
    }


def test_runtime_claim_headers_replace_static_chat_id_with_alias():
    from swe.runtime_invocation_claims import build_runtime_claim_headers

    headers = build_runtime_claim_headers(
        {
            "X-Swe-Chat-Id": "untrusted",
            "chatid": "untrusted",
            "X-Static": "static",
        },
        chat_id="chat-uuid-1",
        include_aliases=True,
    )

    assert headers == {
        "X-Static": "static",
        "x-swe-chat-id": "chat-uuid-1",
        "chatid": "chat-uuid-1",
    }
