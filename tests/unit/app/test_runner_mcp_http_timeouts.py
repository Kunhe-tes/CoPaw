# -*- coding: utf-8 -*-
# pylint: disable=protected-access
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

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


class _FakeTransportContext:
    async def __aenter__(self):
        return ("read-stream", "write-stream")

    async def __aexit__(self, *_args):
        return None


class _FakeSession:
    def __init__(self, *_args):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def initialize(self):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["streamable_http", "sse"])
async def test_http_mcp_connect_uses_merged_headers(
    monkeypatch: pytest.MonkeyPatch,
    transport: str,
) -> None:
    from swe.app.mcp import stateful_client as stateful_client_module
    from swe.app.runner import runner as runner_module

    captured: dict[str, Any] = {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["http_client_kwargs"] = kwargs
            captured["http_client"] = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    def _fake_sse_client(**kwargs):
        captured["sse_client_kwargs"] = kwargs
        return _FakeTransportContext()

    def _fake_streamable_http_client(**kwargs):
        captured["streamable_http_kwargs"] = kwargs
        return _FakeTransportContext()

    monkeypatch.setattr(
        stateful_client_module.httpx,
        "AsyncClient",
        _FakeAsyncClient,
    )
    monkeypatch.setattr(
        stateful_client_module,
        "sse_client",
        _fake_sse_client,
    )
    monkeypatch.setattr(
        stateful_client_module,
        "streamable_http_client",
        _fake_streamable_http_client,
    )
    monkeypatch.setattr(
        stateful_client_module,
        "ClientSession",
        _FakeSession,
    )

    client = await runner_module._create_mcp_client_with_headers(
        MCPClientConfig(
            name="demo",
            transport=transport,
            url=f"https://mcp.example.test/{transport}",
            headers={"X-Static": "static"},
        ),
        passthrough_headers={"Authorization": "Bearer test-token"},
    )

    await client.connect()
    try:
        expected_headers = {
            "X-Static": "static",
            "Authorization": "Bearer test-token",
        }
        if transport == "streamable_http":
            assert captured["http_client_kwargs"]["headers"] == (
                expected_headers
            )
            assert captured["streamable_http_kwargs"]["http_client"] == (
                captured["http_client"]
            )
        else:
            assert captured["sse_client_kwargs"]["headers"] == expected_headers
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_create_streamable_http_mcp_client_uses_explicit_httpx_timeouts(
    monkeypatch,
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

    await runner_module._create_mcp_client_with_headers(
        MCPClientConfig(
            name="demo",
            transport="streamable_http",
            url="https://mcp.example.test/stream",
            headers={"X-Static": "static"},
        ),
        passthrough_headers={"Authorization": "Bearer test-token"},
    )

    assert captured["stateful_client_kwargs"] == {
        "name": "demo",
        "transport": "streamable_http",
        "url": "https://mcp.example.test/stream",
        "headers": {
            "X-Static": "static",
            "Authorization": "Bearer test-token",
        },
        "timeout": runner_module._MCP_HTTP_TIMEOUT_SECONDS,
        "sse_read_timeout": runner_module._MCP_HTTP_SSE_READ_TIMEOUT_SECONDS,
    }


@pytest.mark.asyncio
async def test_create_sse_mcp_client_passes_explicit_read_timeout(
    monkeypatch,
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

    await runner_module._create_mcp_client_with_headers(
        MCPClientConfig(
            name="demo",
            transport="sse",
            url="https://mcp.example.test/sse",
            headers={"X-Static": "static"},
        ),
        passthrough_headers={"Authorization": "Bearer test-token"},
    )

    assert captured["stateful_client_kwargs"] == {
        "name": "demo",
        "transport": "sse",
        "url": "https://mcp.example.test/sse",
        "headers": {
            "X-Static": "static",
            "Authorization": "Bearer test-token",
        },
        "timeout": runner_module._MCP_HTTP_TIMEOUT_SECONDS,
        "sse_read_timeout": runner_module._MCP_HTTP_SSE_READ_TIMEOUT_SECONDS,
    }


@pytest.mark.asyncio
async def test_http_mcp_headers_resolve_explicit_tenant_env_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import runner as runner_module

    monkeypatch.setattr("swe.config.utils.WORKING_DIR", tmp_path)
    monkeypatch.delenv("MCP_TOKEN", raising=False)
    _write_scope_env(
        tmp_path,
        "tenant-a",
        "source-a",
        {"MCP_TOKEN": "tenant-secret"},
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
                    "X-Literal": "${MCP_TOKEN}",
                },
            ),
        )

    assert captured["stateful_client_kwargs"]["headers"] == {
        "Authorization": "Bearer tenant-secret",
        "X-Literal": "${MCP_TOKEN}",
    }
    assert "MCP_TOKEN" not in os.environ


@pytest.mark.asyncio
async def test_http_mcp_env_reference_resolution_is_source_scoped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import runner as runner_module

    monkeypatch.setattr("swe.config.utils.WORKING_DIR", tmp_path)
    _write_scope_env(
        tmp_path,
        "tenant-a",
        "source-a",
        {"MCP_TOKEN": "source-a"},
    )
    _write_scope_env(
        tmp_path,
        "tenant-a",
        "source-b",
        {"MCP_TOKEN": "source-b"},
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

    with tenant_context(tenant_id="tenant-a", source_id="source-b"):
        await runner_module._create_mcp_client_with_headers(
            MCPClientConfig(
                name="demo",
                transport="streamable_http",
                url="https://mcp.example.test/stream",
                headers={"Authorization": "Bearer ${ENV:MCP_TOKEN}"},
            ),
        )

    assert captured["stateful_client_kwargs"]["headers"] == {
        "Authorization": "Bearer source-b",
    }
