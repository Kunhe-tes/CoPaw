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
async def test_ask_plan_clarification_normalizes_form_payload() -> None:
    response = await ask_plan_clarification(
        prompt="Collect customer planning context",
        kind="customer_plan_clarification",
        options=[
            {
                "name": "industry",
                "label": "所在行业",
                "type": "select",
                "options": ["零售/电商", "SaaS/软件服务"],
                "required": True,
            },
            {
                "name": "current_challenges",
                "label": "当前主要挑战",
                "type": "textarea",
                "placeholder": "例如：获客成本高、流失率大",
            },
        ],
        allow_custom_response=True,
    )

    card = response.metadata["plan_interaction_card"]
    assert card["card_type"] == "plan_clarification"
    assert card["kind"] == "form"
    assert card["form_id"] == "customer_plan_clarification"
    assert card["allow_custom_response"] is True
    assert card["fields"] == [
        {
            "id": "industry",
            "label": "所在行业",
            "type": "select",
            "options": [
                {"id": "零售/电商", "label": "零售/电商"},
                {"id": "SaaS/软件服务", "label": "SaaS/软件服务"},
            ],
            "required": True,
        },
        {
            "id": "current_challenges",
            "label": "当前主要挑战",
            "type": "textarea",
            "options": [],
            "placeholder": "例如：获客成本高、流失率大",
            "required": False,
        },
    ]


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


@pytest.mark.asyncio
async def test_submit_proposed_plan_allows_empty_open_questions(
    tmp_path: Path,
) -> None:
    tool = create_submit_proposed_plan_tool(
        request_context={
            "chat_id": "chat-2",
            "session_id": "session-2",
            "turn_id": "turn-2",
            "user_id": "user-2",
        },
        workspace_dir=tmp_path,
    )

    response = await tool(
        title="B2B 企业服务客户经营计划（6个月）",
        summary="将客户经营计划整理为可执行的半年路线图。",
        steps=["保存计划文档", "生成分享版本"],
        risks=[
            "客户成功团队人手不足",
            "竞对低价抢客",
            "涨价说服成本高",
            "跨团队协同成本高",
        ],
        verification=[
            "确认 plan 文件已保存",
            "确认文件内容完整",
        ],
        open_questions=[],
        confidence=0.9,
    )

    card = response.metadata["plan_interaction_card"]
    assert card["card_type"] == "plan_review"
    stored = await JsonProposedPlanStore(tmp_path).get(
        "chat-2",
        card["plan_id"],
    )
    assert stored is not None
    assert stored.open_questions == []
