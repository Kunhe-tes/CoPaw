# -*- coding: utf-8 -*-
"""Channel invariants shared across runtime and management surfaces."""

from collections.abc import Iterable

MANDATORY_CHANNEL_KEYS = ("console",)


def include_mandatory_channels(channel_keys: Iterable[str]) -> tuple[str, ...]:
    """Return mandatory channel keys followed by remaining unique keys."""
    return tuple(dict.fromkeys((*MANDATORY_CHANNEL_KEYS, *channel_keys)))
