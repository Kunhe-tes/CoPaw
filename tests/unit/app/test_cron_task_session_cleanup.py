# -*- coding: utf-8 -*-
"""定时任务会话历史清理回归测试。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from swe.app.crons.manager import AUTO_PAUSE_REASON, CronManager
from swe.app.crons.models import (
    CronJobRequest,
    CronJobSpec,
    DispatchSpec,
    DispatchTarget,
    JobRuntimeSpec,
    JobsFile,
    ScheduleSpec,
)
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.config.context import encode_scope_id


def _job(*, meta: dict[str, Any], enabled: bool = False) -> CronJobSpec:
    return CronJobSpec(
        id="job-1",
        name="Daily task",
        enabled=enabled,
        tenant_id="tenant-a",
        source_id="source-a",
        schedule=ScheduleSpec(
            type="cron",
            cron="0 1 * * *",
            timezone="UTC",
        ),
        task_type="agent",
        request=CronJobRequest(input=[{"content": [{"text": "ping"}]}]),
        dispatch=DispatchSpec(
            type="channel",
            channel="console",
            target=DispatchTarget(user_id="creator", session_id="task-1"),
        ),
        runtime=JobRuntimeSpec(timeout_seconds=30),
        meta=meta,
    )


class _Repo:
    def __init__(self, jobs_file: JobsFile) -> None:
        self.jobs_file = jobs_file
        self.saved: JobsFile | None = None

    async def list_jobs(self) -> list[CronJobSpec]:
        return list(self.jobs_file.jobs)

    async def load(self) -> JobsFile:
        return self.jobs_file

    async def save(self, jobs_file: JobsFile) -> None:
        self.jobs_file = jobs_file
        self.saved = jobs_file


class _Session:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.saved_state: dict[str, Any] | None = None
        self.lock_keys: list[tuple[str, str, float | None]] = []

    @asynccontextmanager
    async def session_write_lock(
        self,
        session_id: str,
        user_id: str = "",
        timeout_seconds: float | None = None,
    ):
        self.lock_keys.append((session_id, user_id, timeout_seconds))
        yield

    async def get_session_state_dict(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict[str, Any]:
        del session_id, user_id, allow_not_exist
        return self.state

    async def save_merged_state(
        self,
        session_id: str,
        user_id: str = "",
        state: dict[str, Any] | None = None,
    ) -> None:
        del session_id, user_id
        self.saved_state = state or {}
        self.state = self.saved_state


class _LockedSession(_Session):
    @asynccontextmanager
    async def session_write_lock(
        self,
        session_id: str,
        user_id: str = "",
        timeout_seconds: float | None = None,
    ):
        self.lock_keys.append((session_id, user_id, timeout_seconds))
        raise TimeoutError("lock busy")
        yield


class _SourceSystemConfigService:
    def __init__(self, enabled: bool = True) -> None:
        self.raw_config = SourceSystemConfig.model_validate(
            {
                "cron_task_session_cleanup": {
                    "enabled": enabled,
                    "retention_days": 30,
                    "cron": "0 1 * * *",
                },
            },
        )

    async def resolve_config(self, source_id: str) -> EffectiveSourceSystemConfig:
        return EffectiveSourceSystemConfig(
            source_id=source_id,
            config=self.raw_config.merged_with_defaults(),
            raw_config=self.raw_config,
            version=1,
        )


def _manager(repo: _Repo, session: _Session) -> CronManager:
    return CronManager(
        repo=repo,
        runner=SimpleNamespace(session=session, workspace_dir=None),
        channel_manager=object(),
        agent_id="default",
        tenant_id=encode_scope_id("tenant-a", "source-a"),
        source_system_config_service=_SourceSystemConfigService(),
    )


@pytest.mark.asyncio
async def test_cleanup_prunes_expired_runs_and_recomputes_task_meta() -> None:
    meta = {
        "task_session_id": "task-1",
        "task_chat_id": "chat-1",
        "creator_user_id": "creator",
        "job_origin": "case",
        "subscription_key": "sub-1",
        "pause_reason": AUTO_PAUSE_REASON,
        "task_has_scheduled_result": True,
        "task_last_scheduled_preview": "old",
        "task_last_scheduled_run_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "task_unread_execution_count": 8,
    }
    repo = _Repo(JobsFile(jobs=[_job(meta=meta)]))
    session = _Session(
        {
            "agent": {
                "memory": {
                    "content": [
                        {"role": "assistant", "content": "expired"},
                        {"role": "assistant", "content": "recent"},
                        {"role": "assistant", "content": "ambiguous"},
                    ],
                },
            },
            "task_runs": [
                {
                    "run_id": "old",
                    "ended_at": "2026-05-01T00:00:00Z",
                    "memory_start": 0,
                    "memory_end": 1,
                    "preview_text": "expired preview",
                },
                {
                    "run_id": "recent",
                    "ended_at": "2026-06-10T00:00:00Z",
                    "memory_start": 1,
                    "memory_end": 2,
                    "preview_text": "recent preview",
                },
                {
                    "run_id": "ambiguous",
                    "memory_start": 2,
                    "memory_end": 3,
                    "preview_text": "ambiguous preview",
                },
            ],
            "task_messages": [
                {"id": "old-message", "timestamp": "2026-05-01T00:00:00Z"},
                {
                    "id": "recent-message",
                    "timestamp": "2026-06-10T00:00:00Z",
                },
                {"id": "ambiguous-message"},
            ],
        },
    )

    result = await _manager(repo, session).run_task_session_cleanup(
        now=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    assert result["sessions_cleaned"] == 1
    assert session.lock_keys == [("task-1", "creator", 5.0)]
    saved_state = session.saved_state
    assert saved_state is not None
    assert saved_state["agent"]["memory"]["content"] == [
        {"role": "assistant", "content": "recent"},
        {"role": "assistant", "content": "ambiguous"},
    ]
    assert saved_state["task_runs"] == [
        {
            "run_id": "recent",
            "ended_at": "2026-06-10T00:00:00Z",
            "memory_start": 0,
            "memory_end": 1,
            "preview_text": "recent preview",
        },
        {
            "run_id": "ambiguous",
            "memory_start": 1,
            "memory_end": 2,
            "preview_text": "ambiguous preview",
        },
    ]
    assert saved_state["task_messages"] == [
        {
            "id": "recent-message",
            "timestamp": "2026-06-10T00:00:00Z",
        },
        {"id": "ambiguous-message"},
    ]
    updated_meta = repo.saved.jobs[0].meta
    assert updated_meta["task_session_id"] == "task-1"
    assert updated_meta["task_chat_id"] == "chat-1"
    assert updated_meta["creator_user_id"] == "creator"
    assert updated_meta["job_origin"] == "case"
    assert updated_meta["subscription_key"] == "sub-1"
    assert updated_meta["pause_reason"] == AUTO_PAUSE_REASON
    assert updated_meta["task_has_scheduled_result"] is True
    assert updated_meta["task_last_scheduled_preview"] == "recent pre"
    assert updated_meta["task_last_scheduled_run_at"] == datetime(
        2026,
        6,
        10,
        tzinfo=timezone.utc,
    )
    assert updated_meta["task_unread_execution_count"] == 0
    assert repo.saved.jobs[0].enabled is False


@pytest.mark.asyncio
async def test_cleanup_clears_session_history_when_all_runs_expire() -> None:
    meta = {
        "task_session_id": "task-1",
        "task_chat_id": "chat-1",
        "creator_user_id": "creator",
        "task_has_scheduled_result": True,
        "task_last_scheduled_preview": "old",
        "task_unread_execution_count": 2,
    }
    repo = _Repo(JobsFile(jobs=[_job(meta=meta)]))
    session = _Session(
        {
            "agent": {
                "memory": {
                    "content": [{"role": "assistant", "content": "expired"}],
                },
            },
            "task_runs": [
                {
                    "run_id": "old",
                    "ended_at": "2026-05-01T00:00:00Z",
                    "memory_start": 0,
                    "memory_end": 1,
                    "preview_text": "expired preview",
                },
            ],
            "task_messages": [
                {"id": "old-message", "timestamp": "2026-05-01T00:00:00Z"},
            ],
            "session_skill_snapshot": {"skill": {"version": "1"}},
        },
    )

    result = await _manager(repo, session).run_task_session_cleanup(
        now=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    assert result["sessions_cleaned"] == 1
    assert session.saved_state == {
        "agent": {"memory": {"content": []}},
        "task_runs": [],
        "task_messages": [],
        "session_skill_snapshot": {"skill": {"version": "1"}},
    }
    updated_meta = repo.saved.jobs[0].meta
    assert updated_meta["task_has_scheduled_result"] is False
    assert updated_meta["task_last_scheduled_preview"] == ""
    assert updated_meta["task_last_scheduled_run_at"] is None
    assert updated_meta["task_unread_execution_count"] == 0
    assert updated_meta["task_session_id"] == "task-1"


@pytest.mark.asyncio
async def test_cleanup_skips_session_when_write_lock_is_unavailable() -> None:
    meta = {
        "task_session_id": "task-1",
        "task_chat_id": "chat-1",
        "creator_user_id": "creator",
        "task_has_scheduled_result": True,
        "task_unread_execution_count": 1,
    }
    repo = _Repo(JobsFile(jobs=[_job(meta=meta)]))
    session = _LockedSession(
        {
            "agent": {"memory": {"content": []}},
            "task_runs": [],
            "task_messages": [],
        },
    )

    result = await _manager(repo, session).run_task_session_cleanup(
        now=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    assert result["sessions_skipped_locked"] == 1
    assert session.saved_state is None
    assert repo.saved is None
