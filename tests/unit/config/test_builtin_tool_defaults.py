# -*- coding: utf-8 -*-
"""Tests for default built-in tool exposure."""

from swe.config.config import BuiltinToolConfig, ToolsConfig


def test_background_process_tools_are_disabled_by_default():
    tools = ToolsConfig().builtin_tools

    assert tools["start_background_process"].enabled is False
    assert tools["list_background_processes"].enabled is False
    assert tools["get_process_output"].enabled is False
    assert tools["stop_background_process"].enabled is False


def test_removed_tools_are_not_added_to_default_config():
    tools = ToolsConfig().builtin_tools

    assert "get_token_usage" not in tools
    assert "set_user_timezone" not in tools
    assert "view_image" not in tools
    assert "view_video" not in tools


def test_removed_tools_are_pruned_from_saved_config():
    config = ToolsConfig(
        builtin_tools={
            "get_token_usage": BuiltinToolConfig(name="get_token_usage"),
            "set_user_timezone": BuiltinToolConfig(name="set_user_timezone"),
            "view_image": BuiltinToolConfig(name="view_image"),
            "view_video": BuiltinToolConfig(name="view_video"),
            "read_file": BuiltinToolConfig(name="read_file"),
        },
    )

    assert "read_file" in config.builtin_tools
    assert "get_token_usage" not in config.builtin_tools
    assert "set_user_timezone" not in config.builtin_tools
    assert "view_image" not in config.builtin_tools
    assert "view_video" not in config.builtin_tools
