# -*- coding: utf-8 -*-
"""工作区本地 Proposed Plan JSON 存储。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Protocol

from .models import PlanReviewDecision, ProposedPlan, ProposedPlanCreate


class ProposedPlanStore(Protocol):
    """可替换的 Proposed Plan 存储接口。"""

    async def create(
        self,
        *,
        chat_id: str,
        session_id: str,
        turn_id: str | None,
        created_by: str | None,
        payload: ProposedPlanCreate,
    ) -> ProposedPlan:
        """创建并持久化一个后端拥有的计划记录。"""

    async def get(self, chat_id: str, plan_id: str) -> ProposedPlan | None:
        """按 chat_id 和 plan_id 读取计划，chat 不匹配时返回 None。"""

    async def find_by_id(self, plan_id: str) -> ProposedPlan | None:
        """按 plan_id 查找计划，用于区分不存在和跨 chat 访问。"""

    async def record_decision(
        self,
        decision: PlanReviewDecision,
    ) -> ProposedPlan:
        """追加用户审核决策并返回更新后的计划。"""


class JsonProposedPlanStore:
    """将 Proposed Plan 保存到 workspace_dir/plans/<chat_id>/。"""

    def __init__(self, workspace_dir: Path | str):
        self._workspace_dir = Path(workspace_dir).expanduser()
        self._plans_dir = self._workspace_dir / "plans"

    async def create(
        self,
        *,
        chat_id: str,
        session_id: str,
        turn_id: str | None,
        created_by: str | None,
        payload: ProposedPlanCreate,
    ) -> ProposedPlan:
        plan = ProposedPlan.new(
            chat_id=chat_id,
            session_id=session_id,
            turn_id=turn_id,
            created_by=created_by,
            payload=payload,
        )
        self._write_plan(plan)
        return plan

    async def get(self, chat_id: str, plan_id: str) -> ProposedPlan | None:
        path = self._plan_path(chat_id=chat_id, plan_id=plan_id)
        if not path.exists():
            return None

        plan = ProposedPlan.model_validate(
            json.loads(path.read_text(encoding="utf-8")),
        )
        if plan.chat_id != chat_id:
            return None
        return plan

    async def find_by_id(self, plan_id: str) -> ProposedPlan | None:
        safe_plan_id = _safe_path_part(plan_id, "plan_id")
        if not self._plans_dir.exists():
            return None
        for path in self._plans_dir.glob(f"*/{safe_plan_id}.json"):
            plan = ProposedPlan.model_validate(
                json.loads(path.read_text(encoding="utf-8")),
            )
            if plan.plan_id == plan_id:
                return plan
        return None

    async def record_decision(
        self,
        decision: PlanReviewDecision,
    ) -> ProposedPlan:
        plan = await self.get(decision.chat_id, decision.plan_id)
        if plan is None:
            raise ValueError("plan not found")

        updated = plan.with_decision(decision)
        self._write_plan(updated)
        return updated

    def _plan_path(self, *, chat_id: str, plan_id: str) -> Path:
        safe_chat_id = _safe_path_part(chat_id, "chat_id")
        safe_plan_id = _safe_path_part(plan_id, "plan_id")
        return self._plans_dir / safe_chat_id / f"{safe_plan_id}.json"

    def _write_plan(self, plan: ProposedPlan) -> None:
        path = self._plan_path(chat_id=plan.chat_id, plan_id=plan.plan_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        payload = plan.model_dump(mode="json")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        shutil.move(str(tmp_path), str(path))


def _safe_path_part(value: str, field_name: str) -> str:
    """拒绝路径分隔符，避免计划读写逃逸出 workspace_dir/plans。"""
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError(f"invalid {field_name}")
    return value
