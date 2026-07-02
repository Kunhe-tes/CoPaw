# -*- coding: utf-8 -*-
"""Plan Mode 结构化交互工具。"""

import json
from pathlib import Path
from typing import Any, Literal

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
_DIRECT_CLARIFICATION_KINDS = frozenset(
    {"single_choice", "multi_choice", "text"},
)
_SUPPORTED_CLARIFICATION_KINDS = _DIRECT_CLARIFICATION_KINDS | {"form"}
_SUPPORTED_FORM_FIELD_TYPES = frozenset(
    {"single_choice", "multi_choice", "text"},
)


def _coerce_json_array(value: Any, field_name: str) -> list[Any]:
    """兼容模型把数组参数再次序列化成 JSON 字符串的情况。"""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"clarification {field_name} must be a valid JSON array",
            ) from error
    if not isinstance(value, list):
        raise ValueError(f"clarification {field_name} must be an array")
    return value


def _normalize_choice_option(option: Any) -> dict[str, Any]:
    """把候选项统一归一成 id/label 结构，便于前端稳定渲染。"""
    if isinstance(option, str):
        return {"id": option, "label": option}
    if not isinstance(option, dict):
        raise ValueError("clarification option must be a string or object")

    option_id = (
        option.get("id")
        or option.get("value")
        or option.get("name")
        or option.get("label")
    )
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
    """兼容 key/name/id 与字符串候选项。"""
    field_id = field.get("id") or field.get("name") or field.get("key")
    if not isinstance(field_id, str) or not field_id.strip():
        raise ValueError("clarification field id is required")

    label = field.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("clarification field label is required")

    raw_type = field.get("type")
    if raw_type is None:
        raw_type = "single_choice" if field.get("options") else "text"
    if not isinstance(raw_type, str) or not raw_type.strip():
        raise ValueError("clarification field type must be a string")
    normalized_type = raw_type.strip().lower()
    if normalized_type not in _SUPPORTED_FORM_FIELD_TYPES:
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

    if normalized_type in {"single_choice", "multi_choice"}:
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
    fields = _coerce_json_array(fields, "fields")
    if not isinstance(fields, list) or any(
        not isinstance(field, dict) for field in fields
    ):
        raise ValueError("clarification fields must be an array of objects")
    return [_normalize_form_field(field) for field in fields]


def _normalize_clarification_kind(
    kind: str,
    raw_options: list[Any],
) -> str:
    """把模型常见的模糊 kind 收敛到卡片协议支持的枚举。"""
    normalized = kind.strip().lower()
    if normalized in _SUPPORTED_CLARIFICATION_KINDS:
        return normalized
    raise ValueError(f"unsupported clarification kind: {kind}")


def _normalize_clarification_payload(
    *,
    kind: str,
    options: list[Any] | str | None,
    fields: list[dict[str, Any]] | str | None,
) -> dict[str, Any]:
    """把旧式 choice/text 和新式表单 payload 收敛为统一卡片模型。"""
    if fields is not None:
        return {
            "kind": "form",
            "form_id": None if kind == "form" else kind,
            "options": [],
            "fields": _normalize_form_fields(fields),
        }

    raw_options = _coerce_json_array(options, "options")
    if kind not in _DIRECT_CLARIFICATION_KINDS and raw_options:
        if all(_looks_like_form_field(option) for option in raw_options):
            return {
                "kind": "form",
                "form_id": kind,
                "options": [],
                "fields": [
                    _normalize_form_field(option) for option in raw_options
                ],
            }

    normalized_kind = _normalize_clarification_kind(kind, raw_options)
    return {
        "kind": normalized_kind,
        "form_id": None,
        "options": [
            _normalize_choice_option(option) for option in raw_options
        ],
        "fields": [],
    }


async def ask_plan_clarification(
    prompt: str,
    kind: Literal["single_choice", "multi_choice", "text", "form"],
    options: list[Any] | str | None = None,
    fields: list[dict[str, Any]] | str | None = None,
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
    ) -> ToolResponse:
        """在没有未决问题时持久化 Proposed Plan，并返回审核卡片元数据。"""
        payload = ProposedPlanCreate(
            title=title,
            summary=summary,
            steps=steps,
            risks=risks,
            verification=verification,
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
