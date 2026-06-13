# -*- coding: utf-8 -*-
"""验证定时任务未读自动暂停的 source 级配置。"""

from __future__ import annotations

from swe.app.crons.manager import AUTO_PAUSE_REASON, CronManager
from swe.app.crons.models import (
    CronJobRequest,
    CronJobSpec,
    DispatchSpec,
    DispatchTarget,
    JobsFile,
    ScheduleSpec,
)
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import bind_source_system_config


def _build_job(*, unread_count: int, enabled: bool = True) -> CronJobSpec:
    return CronJobSpec(
        id="job-1",
        name="daily digest",
        enabled=enabled,
        schedule=ScheduleSpec(cron="0 9 * * mon-fri"),
        request=CronJobRequest(
            input="run report",
            session_id="session-1",
            user_id="user-1",
        ),
        dispatch=DispatchSpec(
            target=DispatchTarget(
                user_id="user-1",
                session_id="session-1",
            ),
        ),
        meta={
            "creator_user_id": "user-1",
            "task_unread_execution_count": unread_count,
        },
    )


def _apply_success(jobs_file: JobsFile) -> tuple[bool, bool]:
    manager = object.__new__(CronManager)
    return manager._apply_task_execution_success(  # pylint: disable=protected-access
        jobs_file,
        "job-1",
        "scheduled result preview",
    )


def _effective_config(config: dict) -> EffectiveSourceSystemConfig:
    return EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate(config).merged_with_defaults(),
        raw_config=SourceSystemConfig.model_validate(config),
        version=1,
    )


def test_default_config_auto_pauses_after_ten_unread_successes():
    """默认开启未读自动暂停，并在第 10 条未读结果后暂停任务。"""
    jobs_file = JobsFile(jobs=[_build_job(unread_count=9)])

    updated, auto_paused = _apply_success(jobs_file)

    assert updated is True
    assert auto_paused is True
    job = jobs_file.jobs[0]
    assert job.enabled is False
    assert job.meta["task_unread_execution_count"] == 10
    assert job.meta["pause_reason"] == AUTO_PAUSE_REASON
    assert job.meta["unread_count_at_pause"] == 10


def test_source_config_can_disable_unread_auto_pause():
    """source 显式关闭后仍统计未读次数，但不自动暂停任务。"""
    jobs_file = JobsFile(jobs=[_build_job(unread_count=99)])
    config = _effective_config(
        {"cron_unread_auto_pause": {"enabled": False, "threshold": 10}},
    )

    with bind_source_system_config(config):
        updated, auto_paused = _apply_success(jobs_file)

    assert updated is True
    assert auto_paused is False
    job = jobs_file.jobs[0]
    assert job.enabled is True
    assert job.meta["task_unread_execution_count"] == 100
    assert "pause_reason" not in job.meta


def test_source_config_can_lower_unread_auto_pause_threshold():
    """source 可独立调低未读暂停条数。"""
    jobs_file = JobsFile(jobs=[_build_job(unread_count=1)])
    config = _effective_config(
        {"cron_unread_auto_pause": {"enabled": True, "threshold": 2}},
    )

    with bind_source_system_config(config):
        updated, auto_paused = _apply_success(jobs_file)

    assert updated is True
    assert auto_paused is True
    job = jobs_file.jobs[0]
    assert job.enabled is False
    assert job.meta["task_unread_execution_count"] == 2
    assert job.meta["unread_count_at_pause"] == 2
