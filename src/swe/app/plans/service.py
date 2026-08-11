# -*- coding: utf-8 -*-
"""计划服务负责封装 chat 归属校验和审核语义。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    PlanReviewDecision,
    PlanReviewDecisionType,
    ProposedPlan,
    ProposedPlanCreate,
)
from .store import ProposedPlanStore


class PlanDecisionConflict(ValueError):
    """计划已经进入终态，不能再接受不同审核决策。"""


@dataclass(frozen=True)
class PlanDecisionResult:
    """记录审核决策后的结果，区分首次写入与幂等重放。"""

    plan: ProposedPlan
    created: bool
    duplicate: bool


class PlanService:
    """围绕 Proposed Plan 存储提供业务级操作。"""

    def __init__(self, store: ProposedPlanStore):
        self._store = store

    async def create_plan(
        self,
        *,
        chat_id: str,
        session_id: str,
        turn_id: str | None,
        created_by: str | None,
        payload: ProposedPlanCreate,
    ) -> ProposedPlan:
        """创建 Proposed Plan，plan_id 始终由后端生成。"""
        return await self._store.create(
            chat_id=chat_id,
            session_id=session_id,
            turn_id=turn_id,
            created_by=created_by,
            payload=payload,
        )

    async def record_decision(
        self,
        *,
        chat_id: str,
        plan_id: str,
        decision: PlanReviewDecisionType,
        feedback: str | None = None,
    ) -> PlanDecisionResult:
        """记录审核动作，并阻止跨 chat 使用 plan_id。"""
        plan = await self._store.get(chat_id, plan_id)
        if plan is None:
            existing_plan = await self._find_plan_outside_chat(plan_id)
            if existing_plan is not None:
                raise ValueError("plan does not belong to chat")
            raise ValueError("plan not found")
        if plan.status != "proposed":
            last_decision = plan.decisions[-1] if plan.decisions else None
            if (
                last_decision is not None
                and last_decision.decision == decision
            ):
                return PlanDecisionResult(
                    plan=plan,
                    created=False,
                    duplicate=True,
                )
            raise PlanDecisionConflict(
                "plan decision conflicts with finalized status",
            )

        review = PlanReviewDecision(
            plan_id=plan.plan_id,
            chat_id=chat_id,
            decision=decision,
            feedback=feedback,
        )
        updated = await self._store.record_decision(review)
        return PlanDecisionResult(
            plan=updated,
            created=True,
            duplicate=False,
        )

    async def load_accepted_plan(
        self,
        chat_id: str,
        plan_id: str,
    ) -> ProposedPlan | None:
        """仅返回当前 chat 下已通过 execute 的计划。"""
        plan = await self._store.get(chat_id, plan_id)
        if plan is None or plan.status != "accepted":
            return None
        return plan

    async def _find_plan_outside_chat(
        self,
        plan_id: str,
    ) -> ProposedPlan | None:
        """通过存储层全局查找，精确区分跨 chat 决策。"""
        return await self._store.find_by_id(plan_id)
