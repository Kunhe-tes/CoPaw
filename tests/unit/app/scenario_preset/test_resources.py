# -*- coding: utf-8 -*-
"""Safety rules for session-scoped marketplace resource materialization."""

from __future__ import annotations

import pytest
from pathlib import Path

from swe.app.scenario_preset.resources import sanitize_mcp_config
from swe.app.scenario_preset.resources import resolve_temporary_mcp_config
from swe.app.scenario_preset.resources import stage_temporary_mcp_config
from swe.app.scenario_preset.resources import stage_temporary_skill_zip


def test_sanitize_mcp_config_rejects_masked_market_secrets() -> None:
    with pytest.raises(ValueError, match="secret"):
        sanitize_mcp_config(
            {
                "transport": "streamable_http",
                "url": "https://mcp.example.test",
                "headers": {"Authorization": "***"},
            },
        )


def test_sanitize_mcp_config_keeps_environment_references_without_resolving() -> None:
    config = sanitize_mcp_config(
        {
            "transport": "stdio",
            "command": "node",
            "args": ["server.js"],
            "env": {"TOKEN": "${ENV:MCP_TOKEN}"},
        },
    )

    assert config == {
        "transport": "stdio",
        "url": "",
        "headers": {},
        "command": "node",
        "args": ["server.js"],
        "env": {"TOKEN": "${ENV:MCP_TOKEN}"},
        "cwd": "",
        "lazy_load": False,
    }


def test_stage_temporary_skill_zip_creates_chat_private_skill(tmp_path: Path) -> None:
    import io
    import zipfile

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "summarize/SKILL.md",
            "---\nname: summarize\ndescription: summary\n---\nUse me.",
        )

    skill_name, skill_path = stage_temporary_skill_zip(
        output.getvalue(),
        resource_id="market-skill-1",
        session_root=tmp_path,
    )

    assert skill_name == "summarize"
    assert skill_path == tmp_path / "market-skill-1" / "summarize" / "SKILL.md"
    assert not (tmp_path / "skill.json").exists()


def test_stage_temporary_mcp_config_keeps_config_out_of_chat_metadata(
    tmp_path: Path,
) -> None:
    path = stage_temporary_mcp_config(
        {"transport": "stdio", "command": "node", "env": {}},
        resource_id="market-mcp-1",
        session_root=tmp_path,
    )

    assert path == tmp_path / "market-mcp-1" / "mcp.json"
    assert '"command": "node"' in path.read_text(encoding="utf-8")


def test_resolve_temporary_mcp_config_omits_missing_tenant_environment(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "swe.app.scenario_preset.resources.get_tenant_runtime_env_value",
        lambda _name: None,
    )

    assert (
        resolve_temporary_mcp_config(
            {"env": {"TOKEN": "${ENV:MISSING_SCENARIO_MCP_TOKEN}"}},
        )
        is None
    )


def test_resolve_temporary_mcp_config_uses_only_tenant_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MCP_TOKEN", "process-secret")
    monkeypatch.setattr(
        "swe.app.scenario_preset.resources.get_tenant_runtime_env_value",
        lambda name: "tenant-secret" if name == "MCP_TOKEN" else None,
    )

    assert resolve_temporary_mcp_config(
        {"env": {"TOKEN": "${ENV:MCP_TOKEN}"}},
    ) == {"env": {"TOKEN": "tenant-secret"}, "headers": {}}
