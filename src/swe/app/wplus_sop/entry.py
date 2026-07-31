# -*- coding: utf-8 -*-
"""Pre-Agent entry classification for the W+ SOP workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ...agents.skill_invocation_detector import SkillInvocationDetector
from ...agents.skills_manager import resolve_effective_skills

WPLUS_SOP_SKILL_NAME = "wplus-sop-miner"
DEFAULT_IMPLICIT_CONFIDENCE = 0.6


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
    user_message: str,
    selected_skill_names: Iterable[object] | None,
    workspace_dir: Path,
    channel: str = "console",
    suppress_implicit: bool = False,
    implicit_confidence: float = DEFAULT_IMPLICIT_CONFIDENCE,
) -> WPlusEntryClassification:
    """Classify W+ before any Chat or Agent run is started.

    Explicit selection uses only the trusted structured skill list. Implicit
    classification reuses the existing synchronous message inferencer, but does
    not start the skill or persist a confirmed association.
    """
    selected = {
        item.strip()
        for item in (selected_skill_names or [])
        if isinstance(item, str) and item.strip()
    }
    if WPLUS_SOP_SKILL_NAME in selected:
        return WPlusEntryClassification(
            should_offer=True,
            mode="explicit",
            confidence=1.0,
        )

    if suppress_implicit or not user_message.strip():
        return WPlusEntryClassification(should_offer=False)

    enabled_skills = resolve_effective_skills(workspace_dir, channel)
    if WPLUS_SOP_SKILL_NAME not in enabled_skills:
        return WPlusEntryClassification(should_offer=False)

    detector = SkillInvocationDetector(workspace_dir=workspace_dir)
    detector.set_enabled_skills(enabled_skills)
    skill_name, confidence = detector.detect_from_user_message(user_message)
    if (
        skill_name == WPLUS_SOP_SKILL_NAME
        and confidence >= implicit_confidence
    ):
        return WPlusEntryClassification(
            should_offer=True,
            mode="implicit",
            confidence=confidence,
        )
    return WPlusEntryClassification(should_offer=False)
