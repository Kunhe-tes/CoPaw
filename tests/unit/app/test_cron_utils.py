# -*- coding: utf-8 -*-
"""定时任务展示时间计算工具的单元测试。"""

from datetime import datetime
from zoneinfo import ZoneInfo

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
