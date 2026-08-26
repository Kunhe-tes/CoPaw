# -*- coding: utf-8 -*-
"""Pre-Agent entry classification for the W+ SOP workspace."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

WPLUS_SOP_SKILL_NAME = "wplus-sop-miner"
_WPLUS_SOP_EXPLICIT_MENTION = re.compile(
    rf"(?<![A-Za-z0-9._%+-])@{re.escape(WPLUS_SOP_SKILL_NAME)}"
    r"(?![A-Za-z0-9_-])",
)


@dataclass(frozen=True)
class WPlusEntryClassification:
    """A preflight result that never starts or confirms a skill."""

    should_offer: bool
    mode: str | None = None
    confidence: float = 0.0


def extract_entry_text(content_parts: Iterable[Any]) -> str:
    """Return user-authored text without trusting visible skill labels."""
    texts: list[str] = []
    for part in content_parts:
        if isinstance(part, dict):
            value = part.get("text")
        else:
            value = getattr(part, "text", None)
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
    return "\n".join(texts)


def classify_wplus_entry(
    *,
    selected_skill_names: Iterable[object] | None,
    message_text: str | None = None,
    suppress_entry: bool = False,
) -> WPlusEntryClassification:
    """Classify W+ before any Chat or Agent run is started.

    A trusted structured selection or an exact user-authored ``@`` mention can
    offer the workspace. Fuzzy text inference is never entry authority.
    """
    if suppress_entry:
        return WPlusEntryClassification(should_offer=False)

    selected = {
        item.strip()
        for item in (selected_skill_names or [])
        if isinstance(item, str) and item.strip()
    }
    has_manual_mention = bool(
        isinstance(message_text, str)
        and _WPLUS_SOP_EXPLICIT_MENTION.search(message_text)
    )
    if WPLUS_SOP_SKILL_NAME in selected or has_manual_mention:
        return WPlusEntryClassification(
            should_offer=True,
            mode="explicit",
            confidence=1.0,
        )
    return WPlusEntryClassification(should_offer=False)
