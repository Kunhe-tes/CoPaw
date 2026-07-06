# -*- coding: utf-8 -*-
"""Tests for tenant-aware MCP HTTP header resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from swe.config.config import MCPClientConfig
from swe.config.context import encode_scope_id, tenant_context
from swe.envs.store import save_envs


def _write_scope_env(
    root: Path,
    tenant_id: str,
    source_id: str,
    envs: dict[str, str],
) -> None:
    scope_id = encode_scope_id(tenant_id, source_id)
    save_envs(envs, root / scope_id / ".secret" / "envs.json")


def test_manager_build_client_keeps_tenant_secret_literal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from swe.app.mcp.manager import MCPClientManager

    monkeypatch.setattr("swe.config.utils.WORKING_DIR", tmp_path)
    monkeypatch.setattr("swe.constant.WORKING_DIR", tmp_path)
    monkeypatch.setenv("HOME", "/home/demo")
    _write_scope_env(
        tmp_path,
        "tenant-a",
        "source-a",
        {"MCP_TOKEN": "abc${HOME}xyz"},
    )
    captured: dict[str, Any] = {}

    class _FakeHttpStatefulClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    with patch(
        "swe.app.mcp.manager.HttpStatefulClient",
        _FakeHttpStatefulClient,
    ):
        with tenant_context(tenant_id="tenant-a", source_id="source-a"):
            MCPClientManager._build_client(
                MCPClientConfig(
                    name="demo",
                    transport="streamable_http",
                    url="https://mcp.example.test/stream",
                    headers={
                        "Authorization": "Bearer ${ENV:MCP_TOKEN}",
                        "X-Home": "dir=${HOME}",
                    },
                ),
            )

    assert captured["headers"] == {
        "Authorization": "Bearer abc${HOME}xyz",
        "X-Home": "dir=/home/demo",
        "x-swe-tenant-id": "tenant-a",
        "tenantid": "tenant-a",
        "x-swe-source-id": "source-a",
        "sourceid": "source-a",
        "x-swe-runtime-scope-id": encode_scope_id("tenant-a", "source-a"),
    }


@pytest.mark.asyncio
async def test_runner_http_client_keeps_tenant_secret_literal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import runner as runner_module

    monkeypatch.setattr("swe.config.utils.WORKING_DIR", tmp_path)
    monkeypatch.setattr("swe.constant.WORKING_DIR", tmp_path)
    monkeypatch.setenv("HOME", "/home/demo")
    _write_scope_env(
        tmp_path,
        "tenant-a",
        "source-a",
        {"MCP_TOKEN": "abc${HOME}xyz"},
    )
    captured: dict[str, Any] = {}

    class _FakeHttpStatefulClient:
        def __init__(self, **kwargs):
            captured["stateful_client_kwargs"] = kwargs

    monkeypatch.setattr(
        runner_module,
        "HttpStatefulClient",
        _FakeHttpStatefulClient,
    )

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        await runner_module._create_mcp_client_with_headers(
            MCPClientConfig(
                name="demo",
                transport="streamable_http",
                url="https://mcp.example.test/stream",
                headers={
                    "Authorization": "Bearer ${ENV:MCP_TOKEN}",
                    "X-Home": "dir=${HOME}",
                },
            ),
        )

    assert captured["stateful_client_kwargs"]["headers"] == {
        "Authorization": "Bearer abc${HOME}xyz",
        "X-Home": "dir=/home/demo",
        "x-swe-tenant-id": "tenant-a",
        "tenantid": "tenant-a",
        "x-swe-source-id": "source-a",
        "sourceid": "source-a",
        "x-swe-runtime-scope-id": encode_scope_id("tenant-a", "source-a"),
    }


@pytest.mark.asyncio
async def test_runner_http_client_injects_runtime_scope_headers_and_dedupes_reserved_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swe.app.runner import runner as runner_module

    captured: dict[str, Any] = {}

    class _FakeHttpStatefulClient:
        def __init__(self, **kwargs):
            captured["stateful_client_kwargs"] = kwargs

    monkeypatch.setattr(
        runner_module,
        "HttpStatefulClient",
        _FakeHttpStatefulClient,
    )

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        await runner_module._create_mcp_client_with_headers(
            MCPClientConfig(
                name="demo",
                transport="streamable_http",
                url="https://mcp.example.test/stream",
                headers={
                    "X-Swe-Tenant-Id": "config-tenant",
                    "X-Swe-Source-Id": "config-source",
                    "X-Static": "static",
                },
            ),
            passthrough_headers={
                "x-swe-source-id": "passthrough-source",
                "X-Swe-Trace-Id": "passthrough-trace",
                "TraceId": "passthrough-compact-trace",
                "Authorization": "Bearer test-token",
            },
            trace_id="trace-1",
        )

    assert captured["stateful_client_kwargs"]["headers"] == {
        "X-Static": "static",
        "Authorization": "Bearer test-token",
        "x-swe-tenant-id": "tenant-a",
        "tenantid": "tenant-a",
        "x-swe-source-id": "source-a",
        "sourceid": "source-a",
        "x-swe-runtime-scope-id": encode_scope_id("tenant-a", "source-a"),
        "x-swe-trace-id": "trace-1",
        "traceid": "trace-1",
    }


@pytest.mark.asyncio
async def test_rebuild_mcp_client_reresolves_scope_headers_on_reconnect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import runner as runner_module
    from swe.agents.react_agent import SWEAgent

    monkeypatch.setenv("HOME", "/home/demo")
    monkeypatch.setattr("swe.config.utils.WORKING_DIR", tmp_path)
    monkeypatch.setattr("swe.constant.WORKING_DIR", tmp_path)
    _write_scope_env(
        tmp_path,
        "tenant-a",
        "source-a",
        {"MCP_TOKEN": "initial-token"},
    )
    captured: list[dict[str, Any]] = []

    class _FakeHttpStatefulClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    with (
        patch(
            "swe.app.runner.runner.HttpStatefulClient",
            _FakeHttpStatefulClient,
        ),
        patch(
            "swe.agents.react_agent.HttpStatefulClient",
            _FakeHttpStatefulClient,
        ),
    ):
        with tenant_context(tenant_id="tenant-a", source_id="source-a"):
            original_client = (
                await runner_module._create_mcp_client_with_headers(
                    MCPClientConfig(
                        name="demo",
                        transport="streamable_http",
                        url="https://mcp.example.test/stream",
                        headers={
                            "Authorization": "Bearer ${ENV:MCP_TOKEN}",
                            "X-Home": "dir=${HOME}",
                        },
                    ),
                    passthrough_headers={"Authorization-Extra": "extra"},
                    session_id="session-1",
                    trace_id="trace-1",
                )
            )

            _write_scope_env(
                tmp_path,
                "tenant-a",
                "source-a",
                {"MCP_TOKEN": "rotated-token"},
            )
            rebuilt = SWEAgent._rebuild_mcp_client(original_client)

    assert rebuilt is not None
    assert captured[0]["headers"] == {
        "Authorization": "Bearer initial-token",
        "X-Home": "dir=/home/demo",
        "Authorization-Extra": "extra",
        "x-swe-tenant-id": "tenant-a",
        "tenantid": "tenant-a",
        "x-swe-source-id": "source-a",
        "sourceid": "source-a",
        "x-swe-runtime-scope-id": encode_scope_id("tenant-a", "source-a"),
        "x-swe-session-id": "session-1",
        "sessionid": "session-1",
        "x-swe-trace-id": "trace-1",
        "traceid": "trace-1",
    }
    assert captured[0]["timeout"] == runner_module._MCP_HTTP_TIMEOUT_SECONDS
    assert (
        captured[0]["sse_read_timeout"]
        == runner_module._MCP_HTTP_SSE_READ_TIMEOUT_SECONDS
    )
    assert captured[1]["headers"] == {
        "Authorization": "Bearer rotated-token",
        "X-Home": "dir=/home/demo",
        "Authorization-Extra": "extra",
        "x-swe-tenant-id": "tenant-a",
        "tenantid": "tenant-a",
        "x-swe-source-id": "source-a",
        "sourceid": "source-a",
        "x-swe-runtime-scope-id": encode_scope_id("tenant-a", "source-a"),
        "x-swe-session-id": "session-1",
        "sessionid": "session-1",
        "x-swe-trace-id": "trace-1",
        "traceid": "trace-1",
    }
    assert captured[1]["timeout"] == runner_module._MCP_HTTP_TIMEOUT_SECONDS
    assert (
        captured[1]["sse_read_timeout"]
        == runner_module._MCP_HTTP_SSE_READ_TIMEOUT_SECONDS
    )
