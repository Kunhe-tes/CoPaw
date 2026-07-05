# -*- coding: utf-8 -*-
"""Runtime SubAgent nickname assignment."""

from __future__ import annotations

import random

BUILTIN_SUBAGENT_NICKNAMES = (
    "研究员",
    "分析员",
    "洞察助手",
    "策略顾问",
    "风险观察员",
)


def assign_subagent_nickname(configured: str | None = None) -> str:
    """Return a configured nickname or a random runtime display nickname."""
    if configured and configured.strip():
        return configured.strip()
    return random.choice(BUILTIN_SUBAGENT_NICKNAMES)
