# -*- coding: utf-8 -*-
"""技能可执行性后台运行器测试。"""

from __future__ import annotations

import asyncio

import pytest

from swe.app.skill_readiness.models import (
    SkillReadinessCheckConfig,
    SkillReadinessCheckResult,
    SkillReadinessConfig,
    SkillReadinessOwner,
)
from swe.app.skill_readiness.runner import SkillReadinessRunner
from swe.app.skill_readiness.strategies import SkillReadinessCheckContext
from swe.config.context import get_current_source_id, get_current_tenant_id


class _ContextRecordingStrategy:
    name = "context_check"
    display_name = "上下文检查"

    def __init__(self):
        self.seen = []

    async def run(self, context, config):
        self.seen.append(
            (
                context.owner.user_id,
                get_current_tenant_id(),
                get_current_source_id(),
            ),
        )
        return SkillReadinessCheckResult(
            check_name=self.name,
            display_name=self.display_name,
            status="pass",
        )


class _Registry:
    def __init__(self, strategy):
        self.strategy = strategy

    async def run_check(self, context, config):
        return await self.strategy.run(context, config)


class _ProgressStore:
    def __init__(self):
        self.progress_updates = []
        self.user_results = []

    async def update_run_progress(self, run_id, **kwargs):
        self.progress_updates.append(kwargs)

    async def record_user_result(self, run_id, user_result):
        self.user_results.append(user_result)


@pytest.mark.asyncio
async def test_user_check_runs_with_owner_tenant_and_source_context():
    """MCP 等策略依赖 contextvars 生成当前 owner 的运行时 header。"""
    strategy = _ContextRecordingStrategy()
    runner = SkillReadinessRunner(
        store=_ProgressStore(),
        registry=_Registry(strategy),
        user_concurrency=1,
    )

    await runner.run(
        run_id="run-1",
        source_id="source-a",
        skill_id="skill-a",
        owners=[SkillReadinessOwner(user_id="alice")],
        config=SkillReadinessConfig(
            checks=[SkillReadinessCheckConfig(name="context_check")],
        ),
    )

    assert strategy.seen == [("alice", "alice", "source-a")]


class _FailingStore(_ProgressStore):
    def __init__(self):
        super().__init__()
        self.bad_started = asyncio.Event()
        self.allow_slow = asyncio.Event()
        self.slow_recorded = False
        self.failed_before_slow = False

    async def update_run_progress(self, run_id, **kwargs):
        if kwargs.get("status") == "failed" and not self.slow_recorded:
            self.failed_before_slow = True
        await super().update_run_progress(run_id, **kwargs)

    async def record_user_result(self, run_id, user_result):
        if user_result.user_id == "bad":
            self.bad_started.set()
            raise RuntimeError("db down")
        await self.allow_slow.wait()
        self.slow_recorded = True
        await super().record_user_result(run_id, user_result)


@pytest.mark.asyncio
async def test_run_waits_for_all_user_tasks_before_marking_failed():
    """单个用户写入异常不能让 run 先 failed 后继续接受其他用户结果。"""
    store = _FailingStore()
    strategy = _ContextRecordingStrategy()
    runner = SkillReadinessRunner(
        store=store,
        registry=_Registry(strategy),
        user_concurrency=2,
    )
    run_task = asyncio.create_task(
        runner.run(
            run_id="run-1",
            source_id="source-a",
            skill_id="skill-a",
            owners=[
                SkillReadinessOwner(user_id="bad"),
                SkillReadinessOwner(user_id="slow"),
            ],
            config=SkillReadinessConfig(
                checks=[SkillReadinessCheckConfig(name="context_check")],
            ),
        ),
    )

    await store.bad_started.wait()
    await asyncio.sleep(0)

    try:
        assert store.failed_before_slow is False
    finally:
        store.allow_slow.set()
        await run_task

    assert store.progress_updates[-1]["status"] == "failed"
    assert store.slow_recorded is True
