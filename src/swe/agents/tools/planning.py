# -*- coding: utf-8 -*-
"""Plan Mode 结构化交互工具。"""

from __future__ import annotations

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


async def ask_plan_clarification(
    prompt: str,
    kind: str,
    options: list[dict[str, Any]] | None = None,
    allow_custom_response: bool = False,
) -> ToolResponse:
    """生成计划澄清卡片，让前端用结构化控件收集下一轮回复。"""
    card = PlanClarificationCard(
        prompt=prompt,
        kind=kind,
        options=options or [],
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
