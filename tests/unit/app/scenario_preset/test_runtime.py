# -*- coding: utf-8 -*-
"""First-message scenario snapshot rules."""

from __future__ import annotations

import pytest
import io
import zipfile
from pathlib import Path

from swe.app.scenario_preset.models import (
    CatalogNode,
    NodeKind,
    ScenarioResourceBinding,
    ScenarioResourceType,
)
from swe.app.scenario_preset.runtime import initialize_scenario_snapshot
from swe.app.scenario_preset.runtime import scenario_snapshot_mcp_configs
from swe.app.scenario_preset.runtime import scenario_snapshot_skill_directives
from swe.app.scenario_preset.runtime import scenario_snapshot_skill_names
from swe.config.config import MCPClientConfig, MCPConfig


class _Service:
    def __init__(self):
        self.nodes = [
            CatalogNode(
                id="domain",
                source_id="source",
                kind=NodeKind.DOMAIN,
                name="文档",
                sort_order=1,
            ),
            CatalogNode(
                id="capability",
                source_id="source",
                kind=NodeKind.CAPABILITY,
                parent_id="domain",
                name="提取",
                sort_order=1,
            ),
            CatalogNode(
                id="scenario",
                source_id="source",
                kind=NodeKind.SCENARIO,
                parent_id="capability",
                name="摘要",
                prompt_draft="总结内容",
                sort_order=1,
            ),
        ]

    async def get_submittable_scenario(self, source_id: str, scenario_id: str):
        assert source_id == "source"
        assert scenario_id == "scenario"
        return (
            self.nodes[-1],
            [
                ScenarioResourceBinding(
                    resource_id="skill-1",
                    resource_type=ScenarioResourceType.SKILL,
                    display_name="摘要技能",
                    sort_order=1,
                ),
            ],
            self.nodes[1],
        )


@pytest.mark.asyncio
async def test_snapshot_contains_only_non_sensitive_resource_identity() -> (
    None
):
    """First submit captures stable IDs and agent, never prompt text or secrets."""
    snapshot = await initialize_scenario_snapshot(
        service=_Service(),
        source_id="source",
        scenario_id="scenario",
        agent_id="agent-a",
    )

    assert snapshot["scenario_id"] == "scenario"
    assert snapshot["capability_name"] == "提取"
    assert snapshot["agent_id"] == "agent-a"
    assert snapshot["resources"] == [
        {"id": "skill-1", "type": "skill", "status": "unresolved"},
    ]
    assert "prompt_draft" not in snapshot


def test_scenario_snapshot_skill_names_uses_server_resolved_skill_name() -> (
    None
):
    snapshot = {
        "resources": [
            {"id": "market-1", "type": "skill", "skill_name": "摘要"},
            {"id": "market-2", "type": "mcp_service"},
        ],
    }

    assert scenario_snapshot_skill_names(snapshot) == ["摘要"]


def test_scenario_snapshot_mcp_configs_returns_only_temporary_entries(
    tmp_path: Path,
) -> None:
    chat_id = "00000000-0000-0000-0000-000000000001"
    config_path = (
        tmp_path / ".scenario_sessions" / chat_id / "mcp-1" / "mcp.json"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"transport": "stdio", "command": "node"}',
        encoding="utf-8",
    )
    snapshot = {
        "resources": [
            {
                "id": "mcp-1",
                "type": "mcp_service",
                "status": "temporary",
                "mcp_client_key": "market-key",
                "mcp_config_path": str(config_path),
                "tools": [{"name": "search"}],
            },
            {
                "id": "mcp-2",
                "type": "mcp_service",
                "status": "persistent",
                "mcp_config_path": str(config_path),
            },
        ],
    }

    assert scenario_snapshot_mcp_configs(
        snapshot,
        workspace_dir=tmp_path,
        chat_id=chat_id,
    ) == [
        {
            "resource_id": "mcp-1",
            "client_key": "market-key",
            "config": {"transport": "stdio", "command": "node"},
            "tools": [{"name": "search"}],
        },
    ]


@pytest.mark.asyncio
async def test_snapshot_prefers_matching_enabled_local_skill(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skills" / "summarize"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nskill_id: skill-1\ndescription: summary\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "skill.json").write_text(
        '{"layout_version": 2, "skills": {"summarize": {"enabled": true, "channels": ["console"]}}}',
        encoding="utf-8",
    )

    snapshot = await initialize_scenario_snapshot(
        service=_Service(),
        source_id="source",
        scenario_id="scenario",
        agent_id="agent-a",
        workspace_dir=tmp_path,
    )

    assert snapshot["resources"] == [
        {
            "id": "skill-1",
            "type": "skill",
            "status": "persistent",
            "skill_name": "summarize",
        },
    ]


@pytest.mark.asyncio
async def test_snapshot_stages_missing_market_skill_for_only_this_chat(
    tmp_path: Path,
) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "summarize/SKILL.md",
            "---\nname: summarize\ndescription: summary\n---\nUse me.",
        )

    class MarketClient:
        async def get_skill_detail(self, **_kwargs):
            return {"version": "1.2.3"}

        async def download_skill(self, **_kwargs):
            return archive.getvalue()

    snapshot = await initialize_scenario_snapshot(
        service=_Service(),
        source_id="source",
        scenario_id="scenario",
        agent_id="agent-a",
        session_resource_root=(
            tmp_path
            / ".scenario_sessions"
            / "00000000-0000-0000-0000-000000000001"
        ),
        market_client=MarketClient(),
    )

    resource = snapshot["resources"][0]
    assert resource["status"] == "temporary"
    assert resource["skill_name"] == "summarize"
    assert resource["version"] == "1.2.3"
    assert Path(resource["skill_path"]).is_file()
    assert not (tmp_path / "skill.json").exists()


def test_snapshot_builds_directive_only_for_chat_private_skill(
    tmp_path: Path,
) -> None:
    chat_id = "00000000-0000-0000-0000-000000000001"
    skill_path = (
        tmp_path
        / ".scenario_sessions"
        / chat_id
        / "skill-1"
        / "summarize"
        / "SKILL.md"
    )
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\ndescription: summary\n---\nUse me.",
        encoding="utf-8",
    )

    directives = scenario_snapshot_skill_directives(
        {
            "resources": [
                {
                    "type": "skill",
                    "status": "temporary",
                    "skill_name": "summarize",
                    "skill_path": str(skill_path),
                },
            ],
        },
        workspace_dir=tmp_path,
        chat_id=chat_id,
    )

    assert len(directives) == 1
    assert directives[0].name == "summarize"
    assert directives[0].path == skill_path


def test_snapshot_rejects_temporary_resource_from_another_chat(
    tmp_path: Path,
) -> None:
    first_chat = "00000000-0000-0000-0000-000000000001"
    other_chat = "00000000-0000-0000-0000-000000000002"
    skill_path = (
        tmp_path
        / ".scenario_sessions"
        / other_chat
        / "skill-1"
        / "summarize"
        / "SKILL.md"
    )
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("---\n---\nUse me.", encoding="utf-8")

    directives = scenario_snapshot_skill_directives(
        {
            "resources": [
                {
                    "type": "skill",
                    "status": "temporary",
                    "skill_name": "summarize",
                    "skill_path": str(skill_path),
                },
            ],
        },
        workspace_dir=tmp_path,
        chat_id=first_chat,
    )

    assert directives == []


def test_snapshot_rejects_symlinked_temporary_skill_path(
    tmp_path: Path,
) -> None:
    chat_id = "00000000-0000-0000-0000-000000000001"
    other_chat = "00000000-0000-0000-0000-000000000002"
    root = tmp_path / ".scenario_sessions"
    (root / chat_id).mkdir(parents=True)
    other_root = root / other_chat / "skill-1" / "summarize"
    other_root.mkdir(parents=True)
    (other_root / "SKILL.md").write_text("---\n---\nUse me.", encoding="utf-8")
    (root / chat_id / "skill-1").symlink_to(
        root / other_chat / "skill-1",
        target_is_directory=True,
    )

    directives = scenario_snapshot_skill_directives(
        {
            "resources": [
                {
                    "type": "skill",
                    "status": "temporary",
                    "skill_name": "summarize",
                    "skill_path": str(
                        root / chat_id / "skill-1" / "summarize" / "SKILL.md",
                    ),
                },
            ],
        },
        workspace_dir=tmp_path,
        chat_id=chat_id,
    )

    assert directives == []


@pytest.mark.asyncio
async def test_snapshot_marks_failed_market_skill_unavailable(
    tmp_path: Path,
) -> None:
    class MarketClient:
        async def get_skill_detail(self, **_kwargs):
            raise RuntimeError("market unavailable")

    snapshot = await initialize_scenario_snapshot(
        service=_Service(),
        source_id="source",
        scenario_id="scenario",
        agent_id="agent-a",
        session_resource_root=tmp_path / ".scenario_sessions" / "chat-a",
        market_client=MarketClient(),
    )

    assert snapshot["resources"][0]["status"] == "unavailable"
    assert snapshot["resources"][0]["unavailable_reason"] == "RuntimeError"


@pytest.mark.asyncio
async def test_snapshot_marks_matching_persistent_mcp_client(
    tmp_path: Path,
) -> None:
    service = _Service()
    service.nodes[-1] = service.nodes[-1].model_copy()
    service.get_submittable_scenario = _mcp_scenario

    config = type(
        "AgentConfig",
        (),
        {
            "mcp": MCPConfig(
                clients={
                    "market-mcp": MCPClientConfig(
                        name="Market MCP",
                        command="echo",
                        source="marketplace:mcp-1",
                        market_client_key="market-key",
                    ),
                },
            ),
        },
    )()

    async def discover(resource_id, _config):
        assert resource_id == "mcp-1"
        return [{"name": "search"}]

    snapshot = await initialize_scenario_snapshot(
        service=service,
        source_id="source",
        scenario_id="scenario",
        agent_id="agent-a",
        workspace_dir=tmp_path,
        agent_config=config,
        mcp_tool_discoverer=discover,
    )

    assert snapshot["resources"] == [
        {
            "id": "mcp-1",
            "type": "mcp_service",
            "status": "persistent",
            "mcp_client_key": "market-key",
            "tools": [{"name": "search"}],
        },
    ]


@pytest.mark.asyncio
async def test_snapshot_resolves_safe_market_mcp_and_freezes_tools(
    tmp_path: Path,
) -> None:
    class MarketClient:
        async def get_mcp_detail(self, *, source_id, item_id, bbk_id):
            assert (source_id, item_id, bbk_id) == ("source", "mcp-1", "100")
            return {
                "client_key": "market-key",
                "version": "2.0.0",
                "config": {
                    "transport": "stdio",
                    "command": "node",
                    "env": {},
                },
            }

    service = _Service()
    service.get_submittable_scenario = _mcp_scenario

    async def discover(resource_id, config):
        assert resource_id == "mcp-1"
        assert config["command"] == "node"
        return [{"name": "search", "inputSchema": {"type": "object"}}]

    snapshot = await initialize_scenario_snapshot(
        service=service,
        source_id="source",
        scenario_id="scenario",
        agent_id="agent-a",
        bbk_id="100",
        market_client=MarketClient(),
        mcp_tool_discoverer=discover,
        session_resource_root=tmp_path / ".scenario_sessions" / "chat-a",
    )

    assert snapshot["resources"][0]["status"] == "temporary"
    assert snapshot["resources"][0]["version"] == "2.0.0"
    assert snapshot["resources"][0]["mcp_client_key"] == "market-key"
    config_path = Path(snapshot["resources"][0]["mcp_config_path"])
    assert config_path.is_file()
    assert "mcp_config" not in snapshot["resources"][0]
    assert snapshot["resources"][0]["tools"] == [
        {"name": "search", "inputSchema": {"type": "object"}},
    ]


async def _mcp_scenario(source_id: str, scenario_id: str):
    return (
        CatalogNode(
            id="scenario",
            source_id=source_id,
            kind=NodeKind.SCENARIO,
            parent_id="capability",
            name="摘要",
            prompt_draft="总结内容",
            sort_order=1,
        ),
        [
            ScenarioResourceBinding(
                resource_id="mcp-1",
                resource_type=ScenarioResourceType.MCP_SERVICE,
                display_name="MCP",
                sort_order=1,
            ),
        ],
        CatalogNode(
            id="capability",
            source_id=source_id,
            kind=NodeKind.CAPABILITY,
            parent_id="domain",
            name="提取",
            sort_order=1,
        ),
    )
