# -*- coding: utf-8 -*-
"""Scenario catalog persistence contract tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.app.scenario_preset.models import CatalogNode, NodeKind
from swe.app.scenario_preset.router import init_scenario_preset_module
from swe.app.scenario_preset.store import ScenarioPresetStore


@pytest.mark.asyncio
async def test_module_initialization_does_not_execute_schema_ddl() -> None:
    """Scenario tables are provisioned by the deployment SQL, never app startup."""
    db = MagicMock(is_connected=True)
    db.execute = AsyncMock()

    await init_scenario_preset_module(db)

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_node_persists_normalized_name_and_stable_id() -> None:
    """Names are display fields while generated IDs remain the stored identity."""
    db = MagicMock(is_connected=True)
    db.execute = AsyncMock()
    node = CatalogNode(
        id="opaque-id",
        source_id="source-a",
        kind=NodeKind.DOMAIN,
        name=" 文档处理 ",
        sort_order=1,
    )

    await ScenarioPresetStore(db).create_node(node)

    _, params = db.execute.await_args.args
    assert params[0] == "opaque-id"
    assert params[4:6] == ("文档处理", "文档处理")
