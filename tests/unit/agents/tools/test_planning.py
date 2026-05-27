# -*- coding: utf-8 -*-
"""测试计划交互工具输出的结构化卡片元数据。"""

from __future__ import annotations

from pathlib import Path

import pytest

from swe.agents.tools.planning import (
    ask_plan_clarification,
    create_submit_proposed_plan_tool,
)
from swe.app.plans import JsonProposedPlanStore


def _text(response) -> str:
    block = response.content[0]
    if isinstance(block, dict):
        return block["text"]
    return block.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "options"),
    [
        (
            "single_choice",
            [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        ),
        (
            "multi_choice",
            [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        ),
        ("text_input", []),
    ],
)
async def test_ask_plan_clarification_emits_card_metadata(
    kind: str,
    options: list[dict[str, str]],
) -> None:
    response = await ask_plan_clarification(
        prompt="Pick a scope",
        kind=kind,
        options=options,
    )

    card = response.metadata["plan_interaction_card"]
    assert card["card_type"] == "plan_clarification"
    assert card["kind"] == kind
    assert card["prompt"] == "Pick a scope"
    assert card["options"] == options
    assert "Planning clarification" in _text(response)


@pytest.mark.asyncio
async def test_submit_proposed_plan_persists_before_review_card(
    tmp_path: Path,
) -> None:
    tool = create_submit_proposed_plan_tool(
        request_context={
            "chat_id": "chat-1",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "user_id": "user-1",
        },
        workspace_dir=tmp_path,
    )

    response = await tool(
        title="Fix failing test",
        summary="Narrow the failing scope and patch it.",
        steps=["Reproduce", "Patch", "Verify"],
        risks=["Hidden regression"],
        verification=["Run pytest"],
        open_questions=["Need frontend coverage?"],
        confidence=0.82,
    )

    card = response.metadata["plan_interaction_card"]
    assert card["card_type"] == "plan_review"
    assert card["plan_id"].startswith("plan-")
    assert card["title"] == "Fix failing test"
    assert "Proposed plan" in _text(response)

    stored = await JsonProposedPlanStore(tmp_path).get(
        "chat-1",
        card["plan_id"],
    )
    assert stored is not None
    assert stored.summary == "Narrow the failing scope and patch it."
