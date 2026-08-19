# -*- coding: utf-8 -*-
from types import SimpleNamespace

from swe.app.runner.runner import _request_scenario_preset_snapshot
from swe.app.runner.runner import _agent_config_with_scenario_mcp
from swe.app.runner.runner import _scenario_snapshot_frozen_mcp_tools
from swe.config.config import Config, MCPConfig


def test_runner_accepts_only_snapshot_restored_from_chat_metadata() -> None:
    snapshot = {"scenario_id": "scenario-a", "resources": []}

    assert (
        _request_scenario_preset_snapshot(
            SimpleNamespace(
                channel_meta={"scenario_preset_snapshot": snapshot},
            ),
        )
        is None
    )
    assert (
        _request_scenario_preset_snapshot(
            SimpleNamespace(
                channel_meta={
                    "scenario_preset_snapshot": snapshot,
                    "scenario_preset_snapshot_source": "chat_meta",
                },
            ),
        )
        == snapshot
    )


def test_runner_overlays_temporary_scenario_mcp_without_mutating_agent_config(
    tmp_path,
):
    original = Config(mcp=MCPConfig(clients={}))
    config_path = tmp_path / ".scenario_sessions" / "chat-a" / "mcp-1" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"transport":"stdio","command":"node","env":{"TOKEN":"${ENV:MCP_TOKEN}"}}',
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
        ],
    }

    effective = _agent_config_with_scenario_mcp(
        original,
        snapshot,
        workspace_dir=tmp_path,
    )

    assert "market-key" not in original.mcp.clients
    assert effective.mcp.clients["market-key"].source == "marketplace:mcp-1"
    assert effective.mcp.clients["market-key"].env == {
        "TOKEN": "${ENV:MCP_TOKEN}",
    }
    assert _scenario_snapshot_frozen_mcp_tools(snapshot) == {
        "market-key": [{"name": "search"}],
    }
