# -*- coding: utf-8 -*-

from swe.config.channel_invariants import (
    MANDATORY_CHANNEL_KEYS,
    include_mandatory_channels,
)


def test_include_mandatory_channels_adds_missing_keys_once():
    assert "console" in MANDATORY_CHANNEL_KEYS
    assert include_mandatory_channels(
        ("optional", MANDATORY_CHANNEL_KEYS[0]),
    ) == (
        *MANDATORY_CHANNEL_KEYS,
        "optional",
    )
