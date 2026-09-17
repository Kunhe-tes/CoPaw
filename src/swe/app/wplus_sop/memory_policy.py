"""Server-owned routing constraints for W+ memory candidates."""

from __future__ import annotations

import re
from typing import Literal

WPlusMemoryTargetScope = Literal["common", "user", "cases"]

_USER_SCOPE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}")


class WPlusMemoryPolicyError(ValueError):
    """Raised when a candidate cannot be bound to an allowed memory target."""


def normalize_anonymous_user_scope(value: object) -> str | None:
    """Accept only an opaque, path-safe caller-provided user scope."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise WPlusMemoryPolicyError("invalid anonymous user_scope")
    normalized = value.strip()
    if _USER_SCOPE_PATTERN.fullmatch(normalized) is None or normalized.isdigit():
        raise WPlusMemoryPolicyError("invalid anonymous user_scope")
    return normalized


def resolve_memory_target(
    memory_type: str,
    *,
    user_scope: str | None,
) -> tuple[WPlusMemoryTargetScope, str]:
    """Bind a typed candidate to its only allowed workspace-relative file."""
    if memory_type == "common_wplus_knowledge":
        return "common", "memory/common-wplus-knowledge.jsonl"
    if memory_type == "sop_case":
        return "cases", "memory/cases/sop-cases.jsonl"
    if memory_type == "user_wplus_usage":
        normalized_scope = normalize_anonymous_user_scope(user_scope)
        if normalized_scope is None:
            raise WPlusMemoryPolicyError(
                "user memory requires caller-provided anonymous user_scope",
            )
        return (
            "user",
            f"memory/users/{normalized_scope}/wplus-usage-preferences.jsonl",
        )
    raise WPlusMemoryPolicyError("invalid W+ memory candidate type")
