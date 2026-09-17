# -*- coding: utf-8 -*-
"""定时任务展示时间计算工具的单元测试。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from swe.app.crons import cron_utils
from swe.app.crons.cron_utils import compute_next_run_times


def test_compute_next_run_times_returns_sequential_times() -> None:
    """连续运行时间应按 cron 表达式向后推进。"""
    run_times = compute_next_run_times(
        "0 9 * * *",
        "Asia/Shanghai",
        count=3,
        now=datetime(2026, 6, 4, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert [item.isoformat() for item in run_times] == [
        "2026-06-04T09:00:00+08:00",
        "2026-06-05T09:00:00+08:00",
        "2026-06-06T09:00:00+08:00",
    ]


def test_compute_next_run_times_handles_nearest_weekday_when_croniter_rejects_w(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """30W should still be displayable if croniter lacks Quartz W support."""

    def reject_nearest_weekday(*_args: object, **_kwargs: object) -> object:
        raise ValueError("unsupported W")

    monkeypatch.setattr(cron_utils, "croniter", reject_nearest_weekday)

    run_times = compute_next_run_times(
        "0 9 30W * *",
        "Asia/Shanghai",
        count=3,
        now=datetime(2026, 6, 30, 13, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert [item.isoformat() for item in run_times] == [
        "2026-07-30T09:00:00+08:00",
        "2026-08-31T09:00:00+08:00",
        "2026-09-30T09:00:00+08:00",
    ]


def test_compute_next_run_times_handles_scheduler_nearest_weekday_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External scheduler format should not break display-only next runs."""

    def reject_nearest_weekday(*_args: object, **_kwargs: object) -> object:
        raise ValueError("unsupported W")

    monkeypatch.setattr(cron_utils, "croniter", reject_nearest_weekday)

    run_times = compute_next_run_times(
        "0 0 9 30W * ?",
        "Asia/Shanghai",
        count=2,
        now=datetime(2026, 6, 30, 13, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert [item.isoformat() for item in run_times] == [
        "2026-07-30T09:00:00+08:00",
        "2026-08-31T09:00:00+08:00",
    ]
