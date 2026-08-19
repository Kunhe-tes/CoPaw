# -*- coding: utf-8 -*-
"""First-message scenario snapshot rules."""

from __future__ import annotations

import pytest
from pathlib import Path

from swe.app.scenario_preset.models import (
    CatalogNode,
    NodeKind,
    ScenarioResourceBinding,
    ScenarioResourceType,
)
from swe.app.scenario_preset.runtime import initialize_scenario_snapshot
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

    snapshot = await initialize_scenario_snapshot(
        service=service,
        source_id="source",
        scenario_id="scenario",
        agent_id="agent-a",
        workspace_dir=tmp_path,
        agent_config=config,
    )

    assert snapshot["resources"] == [
        {
            "id": "mcp-1",
            "type": "mcp_service",
            "status": "persistent",
            "mcp_client_key": "market-key",
        },
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
