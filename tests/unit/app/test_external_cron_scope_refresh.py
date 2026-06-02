# -*- coding: utf-8 -*-
"""外部调度平台 scope 兼容与存量刷新回归测试。"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any

import pytest

from swe.app.crons.manager import CronManager
from swe.app.crons.api import _build_broadcast_job
from swe.app.crons.models import (
    CronJobRequest,
    CronJobSpec,
    DispatchSpec,
    DispatchTarget,
    JobRuntimeSpec,
    ScheduleSpec,
)
from swe.app.crons.scheduler_adapter import RealSchedulerAdapter
from swe.app.routers import internal as internal_router
from swe.config.context import encode_scope_id


class CapturingSchedulerAdapter(RealSchedulerAdapter):
    """捕获外部调度请求，避免测试访问真实平台。"""

    def __init__(self) -> None:
        super().__init__(
            base_url="http://scheduler.local",
            job_group=1,
            author="swe",
            alarm_email="",
            client_no="client",
            client_key="key",
            client_remark="remark",
        )
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def _post(self, path: str, payload: dict[str, Any]) -> dict:
        self.requests.append((path, payload))
        if path.endswith("/add-job"):
            return {"content": "1001"}
        return {"content": "ok"}


def _decode_job_param(value: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(value))


def _sample_job(*, external_id: str | None = None) -> CronJobSpec:
    meta: dict[str, Any] = {}
    if external_id:
        meta["external_job_id"] = external_id
    return CronJobSpec(
        id="job-1",
        name="每日巡检",
        enabled=True,
        tenant_id="tenant-a",
        source_id="source-a",
        scope_id=encode_scope_id("tenant-a", "source-a"),
        schedule=ScheduleSpec(
            type="cron",
            cron="0 9 * * *",
            timezone="Asia/Shanghai",
        ),
        task_type="agent",
        request=CronJobRequest(input=[{"content": [{"text": "ping"}]}]),
        dispatch=DispatchSpec(
            type="channel",
            channel="console",
            target=DispatchTarget(user_id="user-a", session_id="session-a"),
        ),
        runtime=JobRuntimeSpec(timeout_seconds=30),
        meta=meta,
    )


def test_build_broadcast_job_uses_target_tenant_and_current_source() -> None:
    """广播任务必须写入目标租户和当前 source 对应的 runtime scope。"""
    source_job = _sample_job()

    target_job = _build_broadcast_job(
        source_job,
        job_id="job-broadcast",
        target_tenant_id="tenant-b",
        source_id="source-a",
        cron="0 8 * * *",
        timezone_name="Asia/Shanghai",
        offset_minutes=60,
        model_slot=source_job.model_slot,
        model_slot_fallback_reason="",
    )

    assert target_job.tenant_id == "tenant-b"
    assert target_job.source_id == "source-a"
    assert target_job.scope_id == encode_scope_id("tenant-b", "source-a")
    assert target_job.dispatch.target.user_id == "tenant-b"
    assert target_job.request is not None
    assert target_job.request.user_id == "tenant-b"


@pytest.mark.asyncio
async def test_scheduler_payload_uses_logical_tenant_and_source() -> None:
    """调度平台展示和回调参数必须保留原始业务租户和来源。"""
    adapter = CapturingSchedulerAdapter()

    ext_id = await adapter.register_job(
        tenant_id="tenant-a",
        source_id="source-a",
        agent_id="default",
        task_type="job",
        job_id="job-1",
        job_name="每日巡检",
        cron="0 9 * * *",
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    assert ext_id == "1001"
    add_path, payload = adapter.requests[0]
    assert add_path == "/job-admin/v2/add-job"
    assert (
        payload["jobDesc"] == "[SWE] tenant-a/source-a/default/job - 每日巡检"
    )
    job_param = _decode_job_param(payload["jobParam"])
    assert job_param == {
        "tenant_id": "tenant-a",
        "source_id": "source-a",
        "agent_id": "default",
        "task_type": "job",
        "job_id": "job-1",
        "scopeId": "tenant-a-source-a",
        "fromId": "tenant-a",
    }


@pytest.mark.asyncio
async def test_callback_resolves_runtime_scope_from_tenant_and_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回调用原始 tenant/source 推导 scope 后再找 CronManager。"""
    observed: dict[str, Any] = {}

    async def fake_get_cron_manager(manager, tenant_id: str, agent_id: str):
        observed["lookup"] = (tenant_id, agent_id)

        class FakeCronManager:
            async def run_job(
                self,
                job_id: str,
                *,
                is_manual: bool = True,
                source_id: str | None = None,
            ) -> None:
                observed["run_job"] = job_id
                observed["is_manual"] = is_manual
                observed["source_id"] = source_id

        return FakeCronManager()

    monkeypatch.setattr(
        internal_router,
        "_get_cron_manager",
        fake_get_cron_manager,
    )

    params = {
        "tenant_id": "tenant-a",
        "source_id": "source-a",
        "agent_id": "default",
        "task_type": "job",
        "job_id": "job-1",
    }
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(multi_agent_manager=object()),
        ),
    )

    response = await internal_router.internal_cron_callback(
        request=request,
        body={
            "jobParam": base64.urlsafe_b64encode(
                json.dumps(params).encode(),
            ).decode(),
        },
    )

    assert response == {"status": "ok", "task_type": "job"}
    assert observed == {
        "lookup": (encode_scope_id("tenant-a", "source-a"), "default"),
        "run_job": "job-1",
        "is_manual": False,
        "source_id": "source-a",
    }


@pytest.mark.asyncio
async def test_refresh_external_jobs_updates_existing_external_binding(
    tmp_path,
) -> None:
    """存量 external_job_id 任务刷新时必须调用 update-job。"""
    adapter = CapturingSchedulerAdapter()

    class FakeRepo:
        _path = tmp_path / "jobs.json"

        async def list_jobs(self):
            return [_sample_job(external_id="42")]

    manager = CronManager(
        repo=FakeRepo(),
        runner=SimpleNamespace(workspace_dir=None, _workspace=None),
        channel_manager=object(),
        agent_id="default",
        tenant_id=encode_scope_id("tenant-a", "source-a"),
        scheduler_adapter=adapter,
    )

    result = await manager.refresh_external_jobs()

    assert result["updated"] == 1
    assert result["registered"] == 0
    update_path, payload = adapter.requests[0]
    assert update_path == "/job-admin/v2/update-job"
    assert payload["id"] == 42
    assert payload["jobDesc"].startswith("[SWE] tenant-a/source-a/default/job")
    assert _decode_job_param(payload["jobParam"])["source_id"] == "source-a"
