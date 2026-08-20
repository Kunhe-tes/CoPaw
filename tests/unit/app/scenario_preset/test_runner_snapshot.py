# -*- coding: utf-8 -*-
from types import SimpleNamespace

from swe.app.runner.runner import _request_scenario_preset_snapshot
from swe.app.runner.runner import _agent_config_with_scenario_mcp
from swe.app.runner.runner import _scenario_snapshot_frozen_mcp_tools
from swe.app.runner.runner import _without_request_scenario_snapshot
from swe.config.config import Config, MCPClientConfig, MCPConfig


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


def test_runner_discards_client_supplied_scenario_snapshot_before_restore() -> None:
    meta = _without_request_scenario_snapshot(
        {
            "scenario_preset_snapshot": {"scenario_id": "forged"},
            "scenario_preset_snapshot_source": "chat_meta",
            "selected_skill_names": ["ordinary-skill"],
        },
    )

    assert meta == {"selected_skill_names": ["ordinary-skill"]}


def test_runner_overlays_temporary_scenario_mcp_without_mutating_agent_config(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "swe.app.scenario_preset.resources.get_tenant_runtime_env_value",
        lambda name: "tenant-secret" if name == "MCP_TOKEN" else None,
    )
    original = Config(mcp=MCPConfig(clients={}))
    chat_id = "00000000-0000-0000-0000-000000000001"
    config_path = tmp_path / ".scenario_sessions" / chat_id / "mcp-1" / "mcp.json"
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
        chat_id=chat_id,
    )

    assert "market-key" not in original.mcp.clients
    assert effective.mcp.clients["market-key"].source == "marketplace:mcp-1"
    assert effective.mcp.clients["market-key"].env == {"TOKEN": "tenant-secret"}
    assert _scenario_snapshot_frozen_mcp_tools(snapshot, effective) == {
        "market-key": [{"name": "search"}],
    }


def test_runner_skips_frozen_tools_when_mcp_key_maps_to_another_service(
    tmp_path,
) -> None:
    original = Config(
        mcp=MCPConfig(
            clients={
                "market-key": MCPClientConfig(
                    name="Unrelated",
                    command="node",
                    source="manual",
                ),
            },
        ),
    )
    chat_id = "00000000-0000-0000-0000-000000000001"
    config_path = tmp_path / ".scenario_sessions" / chat_id / "mcp-1" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"transport":"stdio","command":"node"}',
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
        chat_id=chat_id,
    )

    assert effective.mcp.clients["market-key"].source == "manual"
    assert _scenario_snapshot_frozen_mcp_tools(snapshot, effective) == {}
