# -*- coding: utf-8 -*-
"""Lazy exports for the config package."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "AgentsRunningConfig": (".config", "AgentsRunningConfig"),
    "Config": (".config", "Config"),
    "ChannelConfig": (".config", "ChannelConfig"),
    "ChannelConfigUnion": (".config", "ChannelConfigUnion"),
    "CONSOLE_CHANNEL_REASON": (".config", "CONSOLE_CHANNEL_REASON"),
    "CONSOLE_CHANNEL_REASON_KEY": (".config", "CONSOLE_CHANNEL_REASON_KEY"),
    "FileGuardConfig": (".config", "FileGuardConfig"),
    "HeartbeatConfig": (".config", "HeartbeatConfig"),
    "SecurityConfig": (".config", "SecurityConfig"),
    "ToolGuardConfig": (".config", "ToolGuardConfig"),
    "ToolGuardRuleConfig": (".config", "ToolGuardRuleConfig"),
    "get_channel_management_constraints": (
        ".config",
        "get_channel_management_constraints",
    ),
    "get_available_channels": (".utils", "get_available_channels"),
    "get_config_path": (".utils", "get_config_path"),
    "get_dream_cron": (".utils", "get_dream_cron"),
    "get_heartbeat_config": (".utils", "get_heartbeat_config"),
    "get_heartbeat_query_path": (".utils", "get_heartbeat_query_path"),
    "get_playwright_chromium_executable_path": (
        ".utils",
        "get_playwright_chromium_executable_path",
    ),
    "get_system_default_browser": (".utils", "get_system_default_browser"),
    "is_running_in_container": (".utils", "is_running_in_container"),
    "load_config": (".utils", "load_config"),
    "normalize_channel_config_set": (
        ".config",
        "normalize_channel_config_set",
    ),
    "normalize_single_channel_config": (
        ".config",
        "normalize_single_channel_config",
    ),
    "save_config": (".utils", "save_config"),
    "strip_channel_management_meta": (
        ".config",
        "strip_channel_management_meta",
    ),
    "update_last_dispatch": (".utils", "update_last_dispatch"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)

    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
