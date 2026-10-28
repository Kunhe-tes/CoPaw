# -*- coding: utf-8 -*-
"""Deterministic intent from the current trusted user input."""

from typing import Any

SUBAGENT_INTENT_KEYWORDS = ("子代理", "子智能体", "subagent", "sub-agent")


def has_subagent_intent(user_text: str | None, enabled: Any = False) -> bool:
    """Expose delegation on a literal keyword or explicit request flag."""
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in {"true", "1", "yes"}
    text = (user_text or "").casefold()
    return bool(enabled) or any(
        word in text for word in SUBAGENT_INTENT_KEYWORDS
    )
