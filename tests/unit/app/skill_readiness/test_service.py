# -*- coding: utf-8 -*-
"""技能可执行性服务测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from swe.app.skill_readiness.models import (
    SkillReadinessConfig,
    SkillReadinessConfigRecord,
    SkillReadinessOwner,
    SkillReadinessRunProgress,
)
from swe.app.skill_readiness.owner_resolver import OwnerLookupResult
from swe.app.skill_readiness.service import (
    SkillReadinessConfigMissing,
    SkillReadinessRunNotFound,
    SkillReadinessService,
)
from swe.app.skill_readiness.strategies import build_default_strategy_registry


class _Store:
    def __init__(self):
        self.config = SkillReadinessConfigRecord(
            skill_id="skill-a",
            config=SkillReadinessConfig.model_validate(
                {"checks": [{"name": "cron_auth_valid"}]},
            ),
            updated_at=datetime.now(),
        )
        self.running = None
        self.created = []
        self.latest = None
        self.list_args = []
        self.get_or_create_calls = []

    async def get_config(self, skill_id):
        if skill_id == "missing":
            return None
        return self.config

    async def get_latest_run(self, source_id, skill_id):
        return self.latest

    async def get_check_summaries(self, run_id):
        return []

    async def get_running_run(self, source_id, skill_id):
        return self.running

    async def create_run(self, source_id, skill_id, config, owner_lookup_summary=None):
        run = SkillReadinessRunProgress(
            run_id="run-created",
            source_id=source_id,
            skill_id=skill_id,
            status="running",
        )
        self.created.append((run, owner_lookup_summary))
        return run

    async def get_or_create_running_run(
        self,
        source_id,
        skill_id,
        config,
        owner_lookup_summary=None,
    ):
        self.get_or_create_calls.append(
            (source_id, skill_id, config, owner_lookup_summary),
        )
        if self.running is not None:
            return self.running, True
        return await self.create_run(
            source_id,
            skill_id,
            config,
            owner_lookup_summary=owner_lookup_summary,
        ), False

    async def update_run_progress(self, run_id, **kwargs):
        return SkillReadinessRunProgress(
            run_id=run_id,
            source_id="source-a",
            skill_id="skill-a",
            status=kwargs.get("status") or "running",
            total_users=kwargs.get("total_users") or 0,
            failure_summary=kwargs.get("failure_summary"),
        )

    async def get_run(self, run_id):
        return SkillReadinessRunProgress(
            run_id=run_id,
            source_id="source-a",
            skill_id="skill-a",
            status="completed",
        )

    async def list_user_results(self, *args, **kwargs):
        self.list_args.append((args, kwargs))
        return [], 0


class _Resolver:
    async def resolve_owners(self, source_id, skill_id):
        return OwnerLookupResult(
            owners=[SkillReadinessOwner(user_id="alice")],
            total_users=1,
            failed_users=1,
            failures=["bob: market down"],
        )


class _AllFailedResolver:
    async def resolve_owners(self, source_id, skill_id):
        return OwnerLookupResult(
            owners=[],
            total_users=2,
            failed_users=2,
            failures=["market down", "tenant source down"],
        )


class _Runner:
    def __init__(self):
        self.scheduled = []

    def schedule(self, **kwargs):
        self.scheduled.append(kwargs)


def _service(store=None, resolver=None, runner=None):
    return SkillReadinessService(
        store=store or _Store(),
        owner_resolver=resolver or _Resolver(),
        registry=build_default_strategy_registry(),
        runner=runner or _Runner(),
    )


@pytest.mark.asyncio
async def test_overview_reports_config_owner_and_latest_summary():
    result = await _service().get_overview("source-a", "skill-a")

    assert result.config_found is True
    assert result.startable is True
    assert result.config_checks[0].display_name == "定时任务鉴权"
    assert result.owner_summary.lookup_failed_users == 1
    assert [owner.user_id for owner in result.owners] == ["alice"]


@pytest.mark.asyncio
async def test_start_run_rejects_missing_config():
    with pytest.raises(SkillReadinessConfigMissing):
        await _service().start_run("source-a", "missing")


@pytest.mark.asyncio
async def test_start_run_reuses_existing_running_run():
    store = _Store()
    store.running = SkillReadinessRunProgress(
        run_id="run-existing",
        source_id="source-a",
        skill_id="skill-a",
        status="running",
    )

    response = await _service(store=store).start_run("source-a", "skill-a")

    assert response.reused is True
    assert response.run.run_id == "run-existing"
    assert store.created == []


@pytest.mark.asyncio
async def test_start_run_schedules_owner_checks_and_records_partial_summary():
    runner = _Runner()
    store = _Store()

    response = await _service(store=store, runner=runner).start_run(
        "source-a",
        "skill-a",
    )

    assert response.reused is False
    assert response.run.total_users == 1
    assert runner.scheduled[0]["partial_failure_summary"] == "bob: market down"


@pytest.mark.asyncio
async def test_start_run_uses_atomic_get_or_create_after_owner_lookup():
    """启动检查时必须通过存储层原子入口避免并发重复创建 running run。"""
    runner = _Runner()
    store = _Store()

    await _service(store=store, runner=runner).start_run("source-a", "skill-a")

    assert len(store.get_or_create_calls) == 1
    assert store.get_or_create_calls[0][0:2] == ("source-a", "skill-a")


@pytest.mark.asyncio
async def test_start_run_marks_run_failed_when_owner_lookup_all_fails():
    runner = _Runner()
    store = _Store()

    response = await _service(
        store=store,
        resolver=_AllFailedResolver(),
        runner=runner,
    ).start_run("source-a", "skill-a")

    assert response.run.status == "failed"
    assert response.run.total_users == 2
    assert response.run.failure_summary == "market down; tenant source down"
    assert runner.scheduled == []


@pytest.mark.asyncio
async def test_results_are_source_scoped():
    with pytest.raises(SkillReadinessRunNotFound):
        await _service().get_results("run-1", source_id="other-source")


@pytest.mark.asyncio
async def test_results_passes_check_filter_to_store():
    store = _Store()

    await _service(store=store).get_results(
        "run-1",
        source_id="source-a",
        status="abnormal",
        check_name="cron_auth_valid",
        check_status="fail",
    )

    _, kwargs = store.list_args[0]
    assert kwargs["status"] == "abnormal"
    assert kwargs["check_name"] == "cron_auth_valid"
    assert kwargs["check_status"] == "fail"
