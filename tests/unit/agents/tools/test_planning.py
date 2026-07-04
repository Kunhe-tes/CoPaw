# -*- coding: utf-8 -*-
"""测试计划交互工具输出的结构化卡片元数据。"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from agentscope.tool import Toolkit

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
        ("text", []),
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
                "type": "single_choice",
                "options": ["零售/电商", "SaaS/软件服务"],
                "required": True,
            },
            {
                "name": "current_challenges",
                "label": "当前主要挑战",
                "type": "text",
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
            "type": "single_choice",
            "options": [
                {"id": "零售/电商", "label": "零售/电商"},
                {"id": "SaaS/软件服务", "label": "SaaS/软件服务"},
            ],
            "required": True,
        },
        {
            "id": "current_challenges",
            "label": "当前主要挑战",
            "type": "text",
            "options": [],
            "placeholder": "例如：获客成本高、流失率大",
            "required": False,
        },
    ]


@pytest.mark.asyncio
async def test_ask_plan_clarification_accepts_string_fields() -> None:
    response = await ask_plan_clarification(
        prompt="Collect customer planning context",
        kind="form",
        fields=(
            '[{"key":"industry","label":"行业/业务类型"},'
            '{"key":"customer_type","label":"客户类型","options":'
            '[{"label":"企业客户 (B2B)","value":"B2B"}]}]'
        ),
        allow_custom_response=True,
    )

    card = response.metadata["plan_interaction_card"]
    assert card["kind"] == "form"
    assert card["fields"] == [
        {
            "id": "industry",
            "label": "行业/业务类型",
            "type": "text",
            "options": [],
            "required": False,
        },
        {
            "id": "customer_type",
            "label": "客户类型",
            "type": "single_choice",
            "options": [{"id": "B2B", "label": "企业客户 (B2B)"}],
            "required": False,
        },
    ]


@pytest.mark.asyncio
async def test_ask_plan_clarification_accepts_name_only_form_fields() -> None:
    response = await ask_plan_clarification(
        prompt="为了给您定制最落地的维护策略，我们需要先对齐几个关键背景。",
        kind="form",
        fields=(
            '[{"name": "机构类型", "description": "您所在的金融机构类型", '
            '"options": ["银行", "券商", "三方财富", "保险", "其他"]}, '
            '{"name": "客户规模", "description": "您目前维护的 100w AUM 客户数量", '
            '"options": ["100户以内", "100-150户", "150-200户", "200户以上"]}, '
            '{"name": "核心痛点", "description": "您目前面临的最大挑战", '
            '"options": ["客户流失/被竞品挖角", "AUM 增长遇到瓶颈", '
            '"日常维护时间不够用", "合规与适当性压力", "产品同质化严重"]}]'
        ),
    )

    card = response.metadata["plan_interaction_card"]
    assert card["kind"] == "form"
    assert card["fields"][0] == {
        "id": "机构类型",
        "label": "机构类型",
        "type": "single_choice",
        "options": [
            {"id": "银行", "label": "银行"},
            {"id": "券商", "label": "券商"},
            {"id": "三方财富", "label": "三方财富"},
            {"id": "保险", "label": "保险"},
            {"id": "其他", "label": "其他"},
        ],
        "required": False,
        "description": "您所在的金融机构类型",
    }


@pytest.mark.asyncio
async def test_ask_plan_clarification_detects_name_only_form_fields_in_options() -> (
    None
):
    response = await ask_plan_clarification(
        prompt="请补充背景。",
        kind="form",
        options=[
            {
                "name": "机构类型",
                "description": "您所在的金融机构类型",
                "options": ["银行", "券商"],
            },
            {
                "name": "核心痛点",
                "options": '["客户流失", "维护时间不够"]',
            },
        ],
    )

    card = response.metadata["plan_interaction_card"]
    assert card["kind"] == "form"
    assert card["fields"][0]["label"] == "机构类型"
    assert card["fields"][0]["type"] == "single_choice"
    assert card["fields"][1]["options"] == [
        {"id": "客户流失", "label": "客户流失"},
        {"id": "维护时间不够", "label": "维护时间不够"},
    ]


@pytest.mark.asyncio
async def test_ask_plan_clarification_reports_indexed_field_id_errors() -> (
    None
):
    with pytest.raises(
        ValueError,
        match=(
            r"clarification fields\[0\] id is required; "
            r"provide id, key, name, label, or title"
        ),
    ):
        await ask_plan_clarification(
            prompt="请补充背景。",
            kind="form",
            fields=[{"description": "缺少字段名"}],
        )


@pytest.mark.asyncio
async def test_ask_plan_clarification_reports_indexed_field_type_errors() -> (
    None
):
    with pytest.raises(
        ValueError,
        match=r"clarification fields\[0\] type must be a string",
    ):
        await ask_plan_clarification(
            prompt="请补充背景。",
            kind="form",
            fields=[{"name": "机构类型", "type": 3}],
        )

    with pytest.raises(
        ValueError,
        match=r"clarification fields\[1\] unsupported type: radio",
    ):
        await ask_plan_clarification(
            prompt="请补充背景。",
            kind="form",
            fields=[
                {"name": "机构类型", "options": ["银行"]},
                {"name": "客户规模", "type": "radio"},
            ],
        )


@pytest.mark.asyncio
async def test_ask_plan_clarification_reports_indexed_field_option_errors() -> (
    None
):
    with pytest.raises(
        ValueError,
        match=(
            r"clarification fields\[0\]\.options\[0\] "
            r"option id is required"
        ),
    ):
        await ask_plan_clarification(
            prompt="请补充背景。",
            kind="form",
            fields=[
                {
                    "name": "机构类型",
                    "options": [{"description": "缺少选项名"}],
                },
            ],
        )


@pytest.mark.asyncio
async def test_ask_plan_clarification_preserves_unified_form_field_types() -> (
    None
):
    response = await ask_plan_clarification(
        prompt="为了把通用方法变成你能直接执行的提分方案，请先回答以下问题。",
        kind="form",
        fields=(
            '[{"key":"grade_level","label":"当前年级","type":"single_choice",'
            '"options":["高一","高二","高三"]},'
            '{"key":"target","label":"目标分数 / 目标院校 / 具体提分目标",'
            '"type":"text"}]'
        ),
        allow_custom_response=True,
    )

    card = response.metadata["plan_interaction_card"]
    assert card["kind"] == "form"
    assert card["fields"] == [
        {
            "id": "grade_level",
            "label": "当前年级",
            "type": "single_choice",
            "options": [
                {"id": "高一", "label": "高一"},
                {"id": "高二", "label": "高二"},
                {"id": "高三", "label": "高三"},
            ],
            "required": False,
        },
        {
            "id": "target",
            "label": "目标分数 / 目标院校 / 具体提分目标",
            "type": "text",
            "options": [],
            "required": False,
        },
    ]


@pytest.mark.asyncio
async def test_ask_plan_clarification_accepts_model_generated_choice_payload_strings() -> (
    None
):
    response = await ask_plan_clarification(
        prompt="升学路径因当前阶段和目标而异。请告诉我你的具体情况：",
        kind="single_choice",
        options=(
            '[{"label": "初中升高中", "description": "中考准备、志愿填报、择校等"}, '
            '{"label": "高中升本科", "description": "高考、强基计划、综合评价、留学等"}, '
            '{"label": "本科升研究生", "description": "考研、保研、留学申请等"}, '
            '{"label": "其他/境外升学", "description": "专升本、博士申请、境外特定国家升学等"}]'
        ),
        allow_custom_response=True,
    )

    card = response.metadata["plan_interaction_card"]
    assert card["kind"] == "single_choice"
    assert card["allow_custom_response"] is True
    assert card["options"] == [
        {
            "id": "初中升高中",
            "label": "初中升高中",
            "description": "中考准备、志愿填报、择校等",
        },
        {
            "id": "高中升本科",
            "label": "高中升本科",
            "description": "高考、强基计划、综合评价、留学等",
        },
        {
            "id": "本科升研究生",
            "label": "本科升研究生",
            "description": "考研、保研、留学申请等",
        },
        {
            "id": "其他/境外升学",
            "label": "其他/境外升学",
            "description": "专升本、博士申请、境外特定国家升学等",
        },
    ]


def test_ask_plan_clarification_tool_schema_guides_choice_kind() -> None:
    toolkit = Toolkit()
    toolkit.register_tool_function(ask_plan_clarification)

    schema = toolkit.tools["ask_plan_clarification"].json_schema
    properties = schema["function"]["parameters"]["properties"]

    assert properties["kind"] == {
        "enum": ["single_choice", "multi_choice", "text", "form"],
        "type": "string",
    }
    assert {"type": "string"} in properties["options"]["anyOf"]
    defs = schema["function"]["parameters"]["$defs"]
    field_schema = defs["PlanClarificationFormFieldInput"]
    assert "name" in field_schema["properties"]
    assert "label" in field_schema["properties"]
    assert "options" in field_schema["properties"]
    assert properties["fields"]["anyOf"][0]["items"] == {
        "$ref": "#/$defs/PlanClarificationFormFieldInput",
    }


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
    )

    card = response.metadata["plan_interaction_card"]
    assert card["card_type"] == "plan_review"
    assert card["plan_id"].startswith("plan-")
    assert card["title"] == "Fix failing test"
    assert "open_questions" not in card
    assert "confidence" not in card
    assert "Proposed plan" in _text(response)

    stored = await JsonProposedPlanStore(tmp_path).get(
        "chat-1",
        card["plan_id"],
    )
    assert stored is not None
    assert stored.summary == "Narrow the failing scope and patch it."


@pytest.mark.asyncio
async def test_submit_proposed_plan_omits_removed_fields_from_signature(
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

    parameters = inspect.signature(tool).parameters

    assert "open_questions" not in parameters
    assert "confidence" not in parameters


def test_submit_proposed_plan_schema_accepts_json_encoded_text_lists(
    tmp_path: Path,
) -> None:
    tool = create_submit_proposed_plan_tool(
        request_context={},
        workspace_dir=tmp_path,
    )
    toolkit = Toolkit()
    toolkit.register_tool_function(tool)

    properties = toolkit.tools["submit_proposed_plan"].json_schema["function"][
        "parameters"
    ]["properties"]

    for field_name in ("steps", "risks", "verification"):
        assert {"items": {"type": "string"}, "type": "array"} in properties[
            field_name
        ]["anyOf"]
        assert {"type": "string"} in properties[field_name]["anyOf"]
