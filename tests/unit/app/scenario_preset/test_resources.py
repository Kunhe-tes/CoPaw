# -*- coding: utf-8 -*-
"""Safety rules for session-scoped marketplace resource materialization."""

from __future__ import annotations

import pytest

from swe.app.scenario_preset.resources import sanitize_mcp_config


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
