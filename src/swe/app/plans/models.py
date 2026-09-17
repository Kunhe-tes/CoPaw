# -*- coding: utf-8 -*-
"""计划模式的持久化模型和交互卡片模型。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ..goals.models import CompletionCriterion, GoalConstraints

PlanStatus = Literal["proposed", "revision_requested", "accepted", "exited"]
PlanReviewDecisionType = Literal["revise", "execute", "exit_plan"]
PlanClarificationKind = Literal[
    "single_choice",
    "multi_choice",
    "text",
    "form",
]
PlanClarificationFieldType = Literal[
    "text",
    "single_choice",
    "multi_choice",
]


def _now_utc() -> datetime:
    """返回带时区的 UTC 当前时间，避免序列化时产生本地时区歧义。"""
    return datetime.now(timezone.utc)


def _new_plan_id() -> str:
    """生成后端拥有的计划标识，防止前端快照成为执行事实来源。"""
    return f"plan-{uuid4().hex[:12]}"


class _StrictPlanModel(BaseModel):
    """所有计划模型默认拒绝未知字段，避免前端注入未声明语义。"""

    model_config = ConfigDict(extra="forbid")


class PlanOption(_StrictPlanModel):
    """计划澄清卡片中的一个可选项。"""

    id: str
    label: str
    description: str | None = None


class PlanClarificationField(_StrictPlanModel):
    """结构化计划澄清表单中的单个字段。"""

    id: str
    label: str
    type: PlanClarificationFieldType
    options: list[PlanOption] = Field(default_factory=list)
    placeholder: str | None = None
    required: bool = False
    description: str | None = None

    @model_validator(mode="after")
    def _validate_field_shape(self) -> "PlanClarificationField":
        """限制字段类型和候选项的组合，避免前端收到矛盾配置。"""
        needs_options = self.type in {"single_choice", "multi_choice"}
        if needs_options and not self.options:
            raise ValueError("choice fields require options")
        if not needs_options and self.options:
            raise ValueError("text fields do not accept options")
        return self


class ProposedPlanCreate(_StrictPlanModel):
    """创建 Proposed Plan 时由模型产出的业务内容。"""

    title: str
    summary: str
    steps: list[str]
    risks: list[str]
    verification: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "steps",
        "risks",
        "verification",
        mode="before",
    )
    @classmethod
    def _decode_json_text_list(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        text = value.strip()
        if not text:
            return value

        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return value

        if isinstance(decoded, list):
            return decoded
        return value

    @field_validator(
        "title",
        "summary",
        mode="after",
    )
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator(
        "steps",
        "risks",
        "verification",
        mode="after",
    )
    @classmethod
    def _non_empty_text_list(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class GoalProposal(_StrictPlanModel):
    """Goal-ready proposal shared by explicit Goal Mode and Plan Mode."""

    card_type: Literal["goal_proposal"] = "goal_proposal"
    objective: str
    completion_criteria: list[CompletionCriterion] = Field(min_length=1)
    constraints: GoalConstraints
    autonomy_boundary: str

    @field_validator("objective", "autonomy_boundary")
    @classmethod
    def _goal_text_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


class PlanReviewDecision(_StrictPlanModel):
    """用户对 Proposed Plan 审核卡片提交的一次决策。"""

    plan_id: str
    chat_id: str
    decision: PlanReviewDecisionType
    feedback: str | None = None
    created_at: datetime = Field(default_factory=_now_utc)


class ProposedPlan(ProposedPlanCreate):
    """后端持久化的 Proposed Plan 记录。"""

    plan_id: str = Field(default_factory=_new_plan_id)
    chat_id: str
    session_id: str
    turn_id: str | None = None
    created_by: str | None = None
    status: PlanStatus = "proposed"
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)
    decisions: list[PlanReviewDecision] = Field(default_factory=list)

    @classmethod
    def new(
        cls,
        *,
        chat_id: str,
        session_id: str,
        turn_id: str | None,
        created_by: str | None,
        payload: ProposedPlanCreate,
    ) -> "ProposedPlan":
        """用后端生成的 plan_id 包装模型输出内容。"""
        return cls(
            **payload.model_dump(),
            chat_id=chat_id,
            session_id=session_id,
            turn_id=turn_id,
            created_by=created_by,
        )

    def with_decision(
        self,
        decision: PlanReviewDecision,
    ) -> "ProposedPlan":
        """追加审核决策并根据决策同步计划状态。"""
        if self.status != "proposed":
            raise ValueError("plan decision is already finalized")
        status_by_decision: dict[PlanReviewDecisionType, PlanStatus] = {
            "revise": "revision_requested",
            "execute": "accepted",
            "exit_plan": "exited",
        }
        return self.model_copy(
            update={
                "status": status_by_decision[decision.decision],
                "decisions": [*self.decisions, decision],
                "updated_at": _now_utc(),
            },
        )


class PlanInteractionCard(_StrictPlanModel):
    """所有计划交互卡片共享的元数据外壳。"""

    card_type: Literal["plan_clarification", "plan_review"]


class PlanClarificationCard(PlanInteractionCard):
    """向用户提问的计划澄清卡片。"""

    card_type: Literal["plan_clarification"] = "plan_clarification"
    prompt: str
    kind: PlanClarificationKind
    options: list[PlanOption] = Field(default_factory=list)
    form_id: str | None = None
    fields: list[PlanClarificationField] = Field(default_factory=list)
    allow_custom_response: bool = True

    @model_validator(mode="after")
    def _validate_clarification_shape(self) -> "PlanClarificationCard":
        """根据卡片种类约束字段，保证前后端使用统一契约。"""
        if self.kind == "form":
            if not self.fields:
                raise ValueError("form clarification requires fields")
            if self.options:
                raise ValueError("form clarification does not use options")
            return self

        if self.fields:
            raise ValueError("non-form clarification does not use fields")
        if self.kind in {"single_choice", "multi_choice"} and not self.options:
            raise ValueError("choice clarification requires options")
        return self


class PlanReviewCard(PlanInteractionCard):
    """展示 Proposed Plan 并收集审核动作的卡片。"""

    card_type: Literal["plan_review"] = "plan_review"
    plan_id: str
    title: str
    summary: str
    steps: list[str]
    risks: list[str]
    verification: list[str]
    submitted_decision: PlanReviewDecisionType | None = None

    @classmethod
    def from_plan(cls, plan: ProposedPlan) -> "PlanReviewCard":
        """从后端持久化计划生成审核卡片，避免依赖前端计划快照。"""
        return cls(
            plan_id=plan.plan_id,
            title=plan.title,
            summary=plan.summary,
            steps=plan.steps,
            risks=plan.risks,
            verification=plan.verification,
        )
