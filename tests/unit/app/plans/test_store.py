# -*- coding: utf-8 -*-
"""覆盖计划 JSON 存储的路径、原子写入和会话级读取。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.app.plans import (
    JsonProposedPlanStore,
    PlanDecisionConflict,
    PlanDecisionResult,
    PlanReviewDecision,
    PlanService,
    ProposedPlanCreate,
)


def _payload(title: str = "Plan title") -> ProposedPlanCreate:
    return ProposedPlanCreate(
        title=title,
        summary="Plan summary",
        steps=["Read code", "Write tests"],
        risks=["Unknown edge case"],
        verification=["Run pytest"],
    )


@pytest.mark.asyncio
async def test_store_writes_plan_under_chat_scoped_directory(
    tmp_path: Path,
) -> None:
    store = JsonProposedPlanStore(tmp_path)
    plan = await store.create(
        chat_id="chat-1",
        session_id="session-1",
        turn_id="turn-1",
        created_by="main-agent",
        payload=_payload(),
    )

    path = tmp_path / "plans" / "chat-1" / f"{plan.plan_id}.json"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["chat_id"] == "chat-1"
    assert raw["plan_id"] == plan.plan_id
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.asyncio
async def test_store_reads_only_matching_chat_scope(tmp_path: Path) -> None:
    store = JsonProposedPlanStore(tmp_path)
    plan = await store.create(
        chat_id="chat-1",
        session_id="session-1",
        turn_id="turn-1",
        created_by="main-agent",
        payload=_payload(),
    )

    assert await store.get("chat-1", plan.plan_id) == plan
    assert await store.get("chat-2", plan.plan_id) is None


@pytest.mark.asyncio
async def test_store_records_decision_and_updates_status(
    tmp_path: Path,
) -> None:
    store = JsonProposedPlanStore(tmp_path)
    plan = await store.create(
        chat_id="chat-1",
        session_id="session-1",
        turn_id="turn-1",
        created_by="main-agent",
        payload=_payload(),
    )
    decision = PlanReviewDecision(
        plan_id=plan.plan_id,
        chat_id="chat-1",
        decision="execute",
        feedback="Looks good",
    )

    updated = await store.record_decision(decision)

    assert updated.status == "accepted"
    assert updated.decisions == [decision]


@pytest.mark.asyncio
async def test_service_validates_chat_ownership(tmp_path: Path) -> None:
    service = PlanService(JsonProposedPlanStore(tmp_path))
    plan = await service.create_plan(
        chat_id="chat-1",
        session_id="session-1",
        turn_id="turn-1",
        created_by="main-agent",
        payload=_payload(),
    )

    with pytest.raises(ValueError, match="plan does not belong to chat"):
        await service.record_decision(
            chat_id="chat-2",
            plan_id=plan.plan_id,
            decision="execute",
        )


@pytest.mark.asyncio
async def test_service_loads_only_accepted_plan(tmp_path: Path) -> None:
    service = PlanService(JsonProposedPlanStore(tmp_path))
    plan = await service.create_plan(
        chat_id="chat-1",
        session_id="session-1",
        turn_id="turn-1",
        created_by="main-agent",
        payload=_payload(),
    )

    assert await service.load_accepted_plan("chat-1", plan.plan_id) is None
    await service.record_decision(
        chat_id="chat-1",
        plan_id=plan.plan_id,
        decision="execute",
    )

    accepted = await service.load_accepted_plan("chat-1", plan.plan_id)
    assert accepted is not None
    assert accepted.plan_id == plan.plan_id


@pytest.mark.asyncio
async def test_service_repeats_same_terminal_decision_idempotently(
    tmp_path: Path,
) -> None:
    """重复提交相同终态决策时不应追加重复 decision。"""
    service = PlanService(JsonProposedPlanStore(tmp_path))
    plan = await service.create_plan(
        chat_id="chat-1",
        session_id="session-1",
        turn_id="turn-1",
        created_by="main-agent",
        payload=_payload(),
    )

    first = await service.record_decision(
        chat_id="chat-1",
        plan_id=plan.plan_id,
        decision="execute",
    )
    second = await service.record_decision(
        chat_id="chat-1",
        plan_id=plan.plan_id,
        decision="execute",
    )

    assert isinstance(first, PlanDecisionResult)
    assert first.created is True
    assert first.duplicate is False
    assert isinstance(second, PlanDecisionResult)
    assert second.created is False
    assert second.duplicate is True
    assert second.plan.status == "accepted"
    assert len(second.plan.decisions) == 1
    assert second.plan.decisions == first.plan.decisions


@pytest.mark.asyncio
async def test_service_rejects_different_decision_after_terminal_status(
    tmp_path: Path,
) -> None:
    """终态计划不能被后续不同决策覆盖。"""
    service = PlanService(JsonProposedPlanStore(tmp_path))
    plan = await service.create_plan(
        chat_id="chat-1",
        session_id="session-1",
        turn_id="turn-1",
        created_by="main-agent",
        payload=_payload(),
    )
    await service.record_decision(
        chat_id="chat-1",
        plan_id=plan.plan_id,
        decision="execute",
    )

    with pytest.raises(PlanDecisionConflict):
        await service.record_decision(
            chat_id="chat-1",
            plan_id=plan.plan_id,
            decision="revise",
        )

    accepted = await service.load_accepted_plan("chat-1", plan.plan_id)
    assert accepted is not None
    assert accepted.status == "accepted"
    assert len(accepted.decisions) == 1
