"""Main-Agent tool for the structured Goal turn boundary protocol."""

from __future__ import annotations

from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from .runtime import GoalTurnResolution


def create_submit_goal_turn_resolution_tool(
    request_context: dict[str, Any],
):
    """Create a request-scoped tool that records one validated resolution."""

    async def submit_goal_turn_resolution(
        decision: str,
        summary: str,
        next_focus: str | None = None,
        evidence_refs: list[str] | None = None,
        wake_conditions: list[str] | None = None,
        completion_proposal: str | None = None,
        blocker: str | None = None,
        affected_criteria: list[str] | None = None,
    ) -> ToolResponse:
        if "goal_turn_resolution" in request_context:
            raise ValueError("Goal turn resolution has already been submitted")
        resolution = GoalTurnResolution(
            decision=decision,
            summary=summary,
            next_focus=next_focus,
            evidence_refs=evidence_refs or [],
            wake_conditions=wake_conditions or [],
            completion_proposal=completion_proposal,
            blocker=blocker,
            affected_criteria=affected_criteria or [],
        )
        request_context["goal_turn_resolution"] = resolution.model_dump(
            mode="json",
        )
        return ToolResponse(
            content=[TextBlock(type="text", text="Goal turn resolution recorded.")],
        )

    return submit_goal_turn_resolution
