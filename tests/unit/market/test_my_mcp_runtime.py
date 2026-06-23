# -*- coding: utf-8 -*-
"""测试 market 内置 MyMCP runtime 的最小行为。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from market.runtime.config_store import (
    AgentProfileConfig,
    AgentProfileRef,
    AgentsRootConfig,
    MCPClientConfig,
    MCPConfig,
    RootAgentsSection,
    load_agent_config,
    save_agent_config,
    save_root_config,
)
from market.app.my_mcp_helpers import resolve_my_mcp_request_context
from market.runtime.context import resolve_effective_tenant_id
from swe.config.context import encode_scope_id


def test_resolve_effective_tenant_id_keeps_non_default_tenant() -> None:
    """非 default tenant 也必须按 source 进入独立 scope。"""
    assert resolve_effective_tenant_id("user_a", "SRC_A") == (
        encode_scope_id("user_a", "SRC_A")
    )


def test_resolve_effective_tenant_id_scopes_default_with_source() -> None:
    """default tenant 在 source 场景下应直达 default_{source}。"""
    assert resolve_effective_tenant_id("default", "SRC_A") == ("default_SRC_A")


def test_resolve_effective_tenant_id_rejects_path_traversal() -> None:
    """market runtime 与主服务一样拒绝危险 identity。"""
    with pytest.raises(ValueError):
        resolve_effective_tenant_id("user_a", "../bad")


def test_my_mcp_context_requires_source_id(tmp_path) -> None:
    """MyMCP 本地状态访问不得缺失 source_id。"""
    request = SimpleNamespace(
        headers={
            "X-User-Id": "user-a",
            "X-Tenant-Id": "user-a",
        },
        app=SimpleNamespace(
            state=SimpleNamespace(
                marketplace=SimpleNamespace(swe_root=tmp_path),
            ),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        resolve_my_mcp_request_context(request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "X-Source-Id header is required"


def test_load_and_save_agent_config_under_market_runtime(tmp_path) -> None:
    """market runtime 应能独立读写 tenant 下的 agent.json。"""
    swe_root = tmp_path / ".swe"
    effective_tenant_id = "default_SRC_A"
    workspace_dir = swe_root / effective_tenant_id / "workspaces" / "default"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    root_config = AgentsRootConfig(
        agents=RootAgentsSection(
            active_agent="default",
            profiles={
                "default": AgentProfileRef(
                    id="default",
                    workspace_dir=str(workspace_dir),
                ),
            },
        ),
    )
    save_root_config(swe_root, effective_tenant_id, root_config)

    agent_config = AgentProfileConfig(
        id="default",
        name="Default Agent",
        workspace_dir=str(workspace_dir),
        mcp=MCPConfig(
            clients={
                "weather-tool": MCPClientConfig(
                    name="weather-tool",
                    transport="stdio",
                    command="npx",
                    args=["-y", "weather-mcp"],
                ),
            },
        ),
    )
    save_agent_config(
        swe_root,
        effective_tenant_id,
        "default",
        agent_config,
    )

    loaded = load_agent_config(
        swe_root,
        effective_tenant_id,
        "default",
    )

    assert loaded.id == "default"
    assert loaded.name == "Default Agent"
    assert "weather-tool" in loaded.mcp.clients
    assert loaded.mcp.clients["weather-tool"].command == "npx"

    raw = json.loads(
        (workspace_dir / "agent.json").read_text(encoding="utf-8"),
    )
    assert raw["mcp"]["clients"]["weather-tool"]["name"] == "weather-tool"


def test_market_runtime_load_agent_config_requires_existing_agent_json(
    tmp_path,
) -> None:
    """market runtime 不应在读取时隐式回填 agent.json。"""
    swe_root = tmp_path / ".swe"
    effective_tenant_id = "default_SRC_A"
    workspace_dir = swe_root / effective_tenant_id / "workspaces" / "default"

    save_root_config(
        swe_root,
        effective_tenant_id,
        AgentsRootConfig(
            agents=RootAgentsSection(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(workspace_dir),
                    ),
                },
            ),
        ),
    )

    with pytest.raises(FileNotFoundError):
        load_agent_config(
            swe_root,
            effective_tenant_id,
            "default",
        )

    assert not (workspace_dir / "agent.json").exists()
