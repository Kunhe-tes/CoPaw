# -*- coding: utf-8 -*-
"""Plan Mode 结构化交互工具。"""

import json
from pathlib import Path
from typing import Any, Literal

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse
from pydantic import BaseModel, ConfigDict, Field

from ...app.plans import (
    PlanClarificationCard,
    GoalProposal,
)
from ...app.goals.models import CompletionCriterion, GoalConstraints

_PLAN_CARD_METADATA_KEY = "plan_interaction_card"
_DIRECT_CLARIFICATION_KINDS = frozenset(
    {"single_choice", "multi_choice", "text"},
)
_SUPPORTED_CLARIFICATION_KINDS = _DIRECT_CLARIFICATION_KINDS | {"form"}
_SUPPORTED_FORM_FIELD_TYPES = frozenset(
    {"single_choice", "multi_choice", "text"},
)
_FORM_FIELD_ID_KEYS = ("id", "key", "name", "label", "title")
_FORM_FIELD_LABEL_KEYS = ("label", "title", "name", "key", "id")
_FORM_FIELD_HINT_KEYS = frozenset(
    {
        "description",
        "label",
        "options",
        "placeholder",
        "required",
        "title",
        "type",
    },
)


class PlanClarificationFormFieldInput(BaseModel):
    """Lenient tool input shape for model-generated clarification form fields."""

    model_config = ConfigDict(extra="allow")

    id: str | None = Field(default=None, description="Stable field id.")
    key: str | None = Field(
        default=None,
        description="Field key alias for id.",
    )
    name: str | None = Field(
        default=None,
        description=(
            "Field name. If label is omitted, this is used as the visible label."
        ),
    )
    label: str | None = Field(default=None, description="Visible field label.")
    title: str | None = Field(
        default=None,
        description="Visible field title alias.",
    )
    type: Literal["single_choice", "multi_choice", "text"] | None = Field(
        default=None,
        description="Control type. Omit it to infer from options.",
    )
    options: list[Any] | str | None = Field(
        default=None,
        description="Choice options as an array or a JSON string array.",
    )
    placeholder: str | None = Field(
        default=None,
        description="Text input placeholder.",
    )
    required: bool | None = Field(
        default=None,
        description="Whether the field is required.",
    )
    description: str | None = Field(
        default=None,
        description="Short help text.",
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


def _field_error_path(index: int | None, suffix: str) -> str:
    if index is None:
        return f"field {suffix}"
    return f"fields[{index}] {suffix}"


def _first_non_empty_text(
    data: dict[str, Any],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _coerce_form_field_object(
    field: Any,
    index: int | None = None,
) -> dict[str, Any]:
    if isinstance(field, BaseModel):
        field = field.model_dump(exclude_none=True)
    if not isinstance(field, dict):
        raise ValueError(
            f"clarification {_field_error_path(index, 'must be an object')}",
        )
    return field


def _normalize_field_choice_options(
    *,
    options: list[Any],
    field_index: int | None,
) -> list[dict[str, Any]]:
    normalized_options: list[dict[str, Any]] = []
    for option_index, option in enumerate(options):
        try:
            normalized_options.append(_normalize_choice_option(option))
        except ValueError as error:
            field_path = (
                f"fields[{field_index}].options[{option_index}]"
                if field_index is not None
                else f"field options[{option_index}]"
            )
            message = str(error)
            if message.startswith("clarification "):
                message = message.removeprefix("clarification ")
            raise ValueError(
                f"clarification {field_path} {message}",
            ) from error
    return normalized_options


def _looks_like_form_field(option: Any) -> bool:
    """根据常见字段约定判断 options 是否实际承载表单字段定义。"""
    if isinstance(option, BaseModel):
        option = option.model_dump(exclude_none=True)
    if not isinstance(option, dict):
        return False

    has_stable_name = any(
        isinstance(option.get(key), str) and option[key].strip()
        for key in ("id", "key", "name")
    )
    has_label_with_type = (
        any(
            isinstance(option.get(key), str) and option[key].strip()
            for key in ("label", "title")
        )
        and isinstance(option.get("type"), str)
        and option["type"].strip()
    )
    has_field_hint = any(key in option for key in _FORM_FIELD_HINT_KEYS)
    return (has_stable_name and has_field_hint) or has_label_with_type


def _normalize_form_field(
    field: dict[str, Any] | PlanClarificationFormFieldInput,
    index: int | None = None,
) -> dict[str, Any]:
    """兼容 key/name/id 与字符串候选项。"""
    field = _coerce_form_field_object(field, index)
    field_id = _first_non_empty_text(field, _FORM_FIELD_ID_KEYS)
    if field_id is None:
        raise ValueError(
            "clarification "
            + _field_error_path(
                index,
                "id is required; provide id, key, name, label, or title",
            ),
        )

    label = _first_non_empty_text(field, _FORM_FIELD_LABEL_KEYS)
    if label is None:
        raise ValueError(
            "clarification "
            + _field_error_path(
                index,
                "label is required; provide label or name",
            ),
        )

    raw_type = field.get("type")
    if raw_type is None:
        raw_type = "single_choice" if field.get("options") else "text"
    if not isinstance(raw_type, str) or not raw_type.strip():
        raise ValueError(
            "clarification "
            + _field_error_path(index, "type must be a string"),
        )
    normalized_type = raw_type.strip().lower()
    if normalized_type not in _SUPPORTED_FORM_FIELD_TYPES:
        raise ValueError(
            "clarification "
            + _field_error_path(index, f"unsupported type: {raw_type}"),
        )

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
        raw_options = _coerce_json_array(
            field.get("options"),
            (
                "fields[].options"
                if index is None
                else f"fields[{index}].options"
            ),
        )
        if not raw_options:
            raise ValueError(
                "clarification "
                + _field_error_path(index, f"{field_id} requires options"),
            )
        normalized["options"] = _normalize_field_choice_options(
            options=raw_options,
            field_index=index,
        )
    return normalized


def _normalize_form_fields(fields: Any) -> list[dict[str, Any]]:
    """兼容模型把表单字段数组序列化为 JSON 字符串的情况。"""
    fields = _coerce_json_array(fields, "fields")
    return [
        _normalize_form_field(field, index)
        for index, field in enumerate(fields)
    ]


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
    fields: list[PlanClarificationFormFieldInput] | str | None,
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
                    _normalize_form_field(option, index)
                    for index, option in enumerate(raw_options)
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
    fields: list[PlanClarificationFormFieldInput] | str | None = None,
    allow_custom_response: bool = True,
) -> ToolResponse:
    """生成计划澄清卡片，让前端用结构化控件收集下一轮回复。

    Choice controls include a system-owned custom-answer path by default.
    Provide only concrete business options; do not add an "other" option.

    Form example:
    fields=[
        {
            "name": "机构类型",
            "label": "机构类型",
            "type": "single_choice",
            "options": ["银行", "券商"],
            "description": "您所在的金融机构类型",
        }
    ]
    """
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
        objective: str,
        completion_criteria: list[CompletionCriterion] | str,
        constraints: GoalConstraints | str,
        autonomy_boundary: str,
    ) -> ToolResponse:
        """Submit a Goal-ready Contract Draft for explicit user confirmation."""
        criteria = _coerce_json_array(
            completion_criteria,
            "completion_criteria",
        )
        parsed_constraints = constraints
        if isinstance(parsed_constraints, str):
            parsed_constraints = json.loads(parsed_constraints)
        proposal = GoalProposal(
            objective=objective,
            completion_criteria=criteria,
            constraints=parsed_constraints,
            autonomy_boundary=autonomy_boundary,
        )
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="Goal Contract Draft submitted for review.",
                ),
            ],
            metadata={
                _PLAN_CARD_METADATA_KEY: proposal.model_dump(mode="json"),
            },
        )

    return submit_proposed_plan
