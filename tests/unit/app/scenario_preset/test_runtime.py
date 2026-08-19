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
