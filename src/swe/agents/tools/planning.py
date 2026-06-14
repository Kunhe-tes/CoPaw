# -*- coding: utf-8 -*-
"""Plan Mode 结构化交互工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from ...app.plans import (
    JsonProposedPlanStore,
    PlanClarificationCard,
    PlanReviewCard,
    PlanService,
    ProposedPlanCreate,
)
from ...constant import WORKING_DIR

_PLAN_CARD_METADATA_KEY = "plan_interaction_card"
_LEGACY_CLARIFICATION_KINDS = frozenset(
    {"single_choice", "multi_choice", "text_input"},
)
_FORM_FIELD_TYPE_ALIASES = {
    "select": "select",
    "multiselect": "multiselect",
    "multi_select": "multiselect",
    "multi_choice": "multiselect",
    "text": "text",
    "text_input": "text",
    "textarea": "textarea",
}


def _normalize_choice_option(option: Any) -> dict[str, Any]:
    """把候选项统一归一成 id/label 结构，便于前端稳定渲染。"""
    if isinstance(option, str):
        return {"id": option, "label": option}
    if not isinstance(option, dict):
        raise ValueError("clarification option must be a string or object")

    option_id = option.get("id") or option.get("value") or option.get("name")
    label = option.get("label") or option.get("name") or option_id
    if not isinstance(option_id, str) or not option_id.strip():
        raise ValueError("clarification option id is required")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("clarification option label is required")

    normalized = {"id": option_id, "label": label}
    description = option.get("description")
    if isinstance(description, str) and description.strip():
        normalized["description"] = description
    return normalized


def _looks_like_form_field(option: Any) -> bool:
    """根据常见字段约定判断 options 是否实际承载表单字段定义。"""
    return (
        isinstance(option, dict)
        and isinstance(option.get("label"), str)
        and isinstance(option.get("type"), str)
        and isinstance(option.get("id") or option.get("name"), str)
    )


def _normalize_form_field(field: dict[str, Any]) -> dict[str, Any]:
    """兼容 key/name/id、字符串候选项和输入类型别名。"""
    field_id = field.get("id") or field.get("name") or field.get("key")
    if not isinstance(field_id, str) or not field_id.strip():
        raise ValueError("clarification field id is required")

    label = field.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("clarification field label is required")

    raw_type = field.get("type")
    if raw_type is None:
        raw_type = "select" if field.get("options") else "text"
    if not isinstance(raw_type, str) or not raw_type.strip():
        raise ValueError("clarification field type must be a string")
    normalized_type = _FORM_FIELD_TYPE_ALIASES.get(raw_type.strip().lower())
    if normalized_type is None:
        raise ValueError(f"unsupported clarification field type: {raw_type}")

    normalized: dict[str, Any] = {
        "id": field_id,
        "label": label,
        "type": normalized_type,
        "required": bool(field.get("required", False)),
    }
    placeholder = field.get("placeholder")
    if isinstance(placeholder, str) and placeholder.strip():
        normalized["placeholder"] = placeholder
    description = field.get("description")
    if isinstance(description, str) and description.strip():
        normalized["description"] = description

    if normalized_type in {"select", "multiselect"}:
        raw_options = field.get("options")
        if not isinstance(raw_options, list) or not raw_options:
            raise ValueError(
                f"clarification field {field_id} requires options",
            )
        normalized["options"] = [
            _normalize_choice_option(option) for option in raw_options
        ]
    return normalized


def _normalize_form_fields(fields: Any) -> list[dict[str, Any]]:
    """兼容模型把表单字段数组序列化为 JSON 字符串的情况。"""
    if isinstance(fields, str):
        try:
            fields = json.loads(fields)
        except json.JSONDecodeError as error:
            raise ValueError(
                "clarification fields must be a valid JSON array",
            ) from error
    if not isinstance(fields, list) or any(
        not isinstance(field, dict) for field in fields
    ):
        raise ValueError("clarification fields must be an array of objects")
    return [_normalize_form_field(field) for field in fields]


def _normalize_clarification_payload(
    *,
    kind: str,
    options: list[dict[str, Any]] | None,
    fields: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """把旧式 choice/text 和新式表单 payload 收敛为统一卡片模型。"""
    if fields is not None:
        return {
            "kind": "form",
            "form_id": None if kind == "form" else kind,
            "options": [],
            "fields": _normalize_form_fields(fields),
        }

    raw_options = options or []
    if kind not in _LEGACY_CLARIFICATION_KINDS and raw_options:
        if all(_looks_like_form_field(option) for option in raw_options):
            return {
                "kind": "form",
                "form_id": kind,
                "options": [],
                "fields": [
                    _normalize_form_field(option) for option in raw_options
                ],
            }

    return {
        "kind": kind,
        "form_id": None,
        "options": [
            _normalize_choice_option(option) for option in raw_options
        ],
        "fields": [],
    }


async def ask_plan_clarification(
    prompt: str,
    kind: str,
    options: list[dict[str, Any]] | None = None,
    fields: list[dict[str, Any]] | None = None,
    allow_custom_response: bool = False,
) -> ToolResponse:
    """生成计划澄清卡片，让前端用结构化控件收集下一轮回复。"""
    payload = _normalize_clarification_payload(
        kind=kind,
        options=options,
        fields=fields,
    )
    card = PlanClarificationCard(
        prompt=prompt,
        kind=payload["kind"],
        options=payload["options"],
        form_id=payload["form_id"],
        fields=payload["fields"],
        allow_custom_response=allow_custom_response,
    )
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text="Planning clarification requested.",
            ),
        ],
        metadata={
            _PLAN_CARD_METADATA_KEY: card.model_dump(
                mode="json",
                exclude_none=True,
            ),
        },
    )


def create_submit_proposed_plan_tool(
    *,
    request_context: dict[str, Any],
    workspace_dir: Path | str | None,
):
    """创建带请求上下文的 Proposed Plan 提交工具。"""

    async def submit_proposed_plan(
        title: str,
        summary: str,
        steps: list[str],
        risks: list[str],
        verification: list[str],
        open_questions: list[str],
        confidence: float,
    ) -> ToolResponse:
        """持久化 Proposed Plan，并返回计划审核卡片元数据。"""
        payload = ProposedPlanCreate(
            title=title,
            summary=summary,
            steps=steps,
            risks=risks,
            verification=verification,
            open_questions=open_questions,
            confidence=confidence,
        )
        service = PlanService(
            JsonProposedPlanStore(Path(workspace_dir or WORKING_DIR)),
        )
        plan = await service.create_plan(
            chat_id=str(request_context.get("chat_id") or ""),
            session_id=str(request_context.get("session_id") or ""),
            turn_id=request_context.get("turn_id"),
            created_by=str(request_context.get("user_id") or "main-agent"),
            payload=payload,
        )
        card = PlanReviewCard.from_plan(plan)
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="Proposed plan submitted for review.",
                ),
            ],
            metadata={
                _PLAN_CARD_METADATA_KEY: card.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
            },
        )

    return submit_proposed_plan
