# -*- coding: utf-8 -*-
"""Tests for tenant-aware MCP HTTP header resolution."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
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
    }


def test_rebuild_mcp_client_keeps_tenant_secret_literal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from swe.agents.react_agent import SWEAgent

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

    original_client = SimpleNamespace(
        _swe_rebuild_info={
            "name": "demo",
            "transport": "streamable_http",
            "url": "https://mcp.example.test/stream",
            "headers": {
                "Authorization": "Bearer ${ENV:MCP_TOKEN}",
                "X-Home": "dir=${HOME}",
            },
        },
    )

    with patch(
        "swe.agents.react_agent.HttpStatefulClient",
        _FakeHttpStatefulClient,
    ):
        with tenant_context(tenant_id="tenant-a", source_id="source-a"):
            SWEAgent._rebuild_mcp_client(original_client)

    assert captured["headers"] == {
        "Authorization": "Bearer abc${HOME}xyz",
        "X-Home": "dir=/home/demo",
    }
