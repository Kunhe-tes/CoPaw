# -*- coding: utf-8 -*-
"""Server-owned delegation authority for a Goal Contract draft."""

from typing import Any

GOAL_DRAFT_DELEGATION_META_KEY = "goal_draft_subagent_delegation_enabled"


def is_goal_draft_request(request: Any) -> bool:
    """Keep draft authority scoped to explicit Goal drafting requests."""
    meta = getattr(request, "channel_meta", None) or {}
    return bool(
        meta.get("goal_mode_enabled") is True
        and meta.get("mode") != "plan"
        and not meta.get("selected_expert_id")
        and not getattr(request, "selected_expert_id", None)
        and not meta.get("goal_id")
        and getattr(request, "execution_origin", None) != "scheduled",
    )
