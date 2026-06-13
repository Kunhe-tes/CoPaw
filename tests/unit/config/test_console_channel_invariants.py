# -*- coding: utf-8 -*-

from swe.config.config import (
    ChannelConfig,
    ConsoleConfig,
    get_channel_management_constraints,
    normalize_channel_config_set,
    normalize_single_channel_config,
)


def test_normalize_single_channel_config_forces_console_enabled_true():
    normalized = normalize_single_channel_config(
        "console",
        {"enabled": False, "bot_prefix": "[BOT]"},
    )

    assert normalized["enabled"] is True
    assert normalized["bot_prefix"] == "[BOT]"


def test_normalize_channel_config_set_materializes_console_when_missing():
    normalized = normalize_channel_config_set(
        None,
        materialize_missing_console=True,
    )

    assert isinstance(normalized, ChannelConfig)
    assert isinstance(normalized.console, ConsoleConfig)
    assert normalized.console.enabled is True


def test_console_channel_constraints_are_sparse_and_read_only():
    constraints = get_channel_management_constraints("console")

    assert constraints == {
        "enabled": {
            "readOnly": True,
            "enforcedValue": True,
            "reasonKey": "channels.constraints.console_enabled_mandatory",
            "reason": (
                "Console channel is system-managed and always enabled."
            ),
        },
    }
