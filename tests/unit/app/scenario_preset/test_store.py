# -*- coding: utf-8 -*-
"""Scenario catalog persistence contract tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.app.scenario_preset.models import CatalogNode, NodeKind
from swe.app.scenario_preset.store import ScenarioPresetStore


@pytest.mark.asyncio
async def test_initialize_uses_null_safe_root_name_uniqueness() -> None:
    """Root domains must be unique despite MySQL treating NULL unique keys loosely."""
    db = MagicMock(is_connected=True)
    db.execute = AsyncMock()

    await ScenarioPresetStore(db).initialize()

    ddl = "\n".join(call.args[0] for call in db.execute.await_args_list)
    assert "parent_key VARCHAR(64) AS (IFNULL(parent_id, '')) STORED" in ddl
    assert "(source_id, parent_key, normalized_name)" in ddl


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
