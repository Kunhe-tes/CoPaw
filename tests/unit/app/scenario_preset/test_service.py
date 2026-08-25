# -*- coding: utf-8 -*-
"""Scenario preset catalog service rules."""

from __future__ import annotations

import pytest

from swe.app.scenario_preset.models import CatalogNode, NodeKind
from swe.app.scenario_preset.service import ScenarioPresetCatalogService


class _Store:
    def __init__(self, nodes: list[CatalogNode]):
        self.nodes = nodes

    async def list_nodes(self, source_id: str) -> list[CatalogNode]:
        return [node for node in self.nodes if node.source_id == source_id]


@pytest.mark.asyncio
async def test_effective_catalog_exposes_only_complete_enabled_paths() -> None:
    """A disabled ancestor or incomplete branch must not reach new-chat UI."""
    store = _Store(
        [
            CatalogNode(
                id="domain-a",
                source_id="source-a",
                kind=NodeKind.DOMAIN,
                name="文档",
                sort_order=1,
            ),
            CatalogNode(
                id="capability-a",
                source_id="source-a",
                kind=NodeKind.CAPABILITY,
                parent_id="domain-a",
                name="提取",
                sort_order=1,
            ),
            CatalogNode(
                id="scenario-a",
                source_id="source-a",
                kind=NodeKind.SCENARIO,
                parent_id="capability-a",
                name="关键信息",
                prompt_draft="提取重点",
                sort_order=1,
            ),
            CatalogNode(
                id="domain-disabled",
                source_id="source-a",
                kind=NodeKind.DOMAIN,
                name="已停用",
                is_active=False,
                sort_order=2,
            ),
            CatalogNode(
                id="capability-hidden",
                source_id="source-a",
                kind=NodeKind.CAPABILITY,
                parent_id="domain-disabled",
                name="隐藏能力",
                sort_order=1,
            ),
            CatalogNode(
                id="scenario-hidden",
                source_id="source-a",
                kind=NodeKind.SCENARIO,
                parent_id="capability-hidden",
                name="隐藏场景",
                prompt_draft="不应出现",
                sort_order=1,
            ),
            CatalogNode(
                id="domain-incomplete",
                source_id="source-a",
                kind=NodeKind.DOMAIN,
                name="不完整",
                sort_order=3,
            ),
        ],
    )

    catalog = await ScenarioPresetCatalogService(store).get_effective_catalog(
        "source-a",
    )

    assert [domain.id for domain in catalog.domains] == ["domain-a"]
    assert catalog.domains[0].capabilities[0].scenarios[0].id == "scenario-a"


def test_catalog_node_name_is_trimmed_and_requires_parent_for_non_domain() -> (
    None
):
    """Stable node data cannot contain ambiguous names or invalid tree edges."""
    assert (
        CatalogNode(
            id="domain-a",
            source_id="source-a",
            kind=NodeKind.DOMAIN,
            name=" 文档 ",
            sort_order=1,
        ).name
        == "文档"
    )
    with pytest.raises(ValueError, match="parent_id"):
        CatalogNode(
            id="capability-a",
            source_id="source-a",
            kind=NodeKind.CAPABILITY,
            name="提取",
            sort_order=1,
        )
