from __future__ import annotations

import pytest

from swe.app.goals.turn_tool import create_submit_goal_turn_resolution_tool


@pytest.mark.asyncio
async def test_resolution_tool_records_a_validated_turn_boundary() -> None:
    context: dict[str, object] = {}
    tool = create_submit_goal_turn_resolution_tool(context)

    response = await tool(
        decision="continue",
        summary="Implemented the first slice",
        next_focus="Run verification",
        affected_criteria=["criterion-1"],
    )

    assert "Goal turn resolution" in response.content[0]["text"]
    assert context["goal_turn_resolution"] == {
        "decision": "continue",
        "summary": "Implemented the first slice",
        "next_focus": "Run verification",
        "evidence_refs": [],
        "wake_conditions": [],
        "completion_proposal": None,
        "blocker": None,
        "affected_criteria": ["criterion-1"],
    }


@pytest.mark.asyncio
async def test_resolution_tool_rejects_a_second_boundary_in_one_turn() -> None:
    context: dict[str, object] = {}
    tool = create_submit_goal_turn_resolution_tool(context)
    await tool(decision="continue", summary="first")

    with pytest.raises(ValueError, match="already"):
        await tool(decision="continue", summary="second")
