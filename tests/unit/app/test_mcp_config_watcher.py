# -*- coding: utf-8 -*-
"""Tests for MCP config watcher defaults."""

from unittest.mock import Mock

from swe.app.mcp.watcher import MCPConfigWatcher


def test_mcp_config_watcher_default_poll_interval_is_conservative() -> None:
    watcher = MCPConfigWatcher(
        mcp_manager=Mock(),
        config_loader=Mock(),
    )

    assert watcher._poll_interval == 10.0
