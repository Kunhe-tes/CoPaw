# -*- coding: utf-8 -*-
"""外部调度平台 cron 表达式转换规则测试。"""

from swe.app.crons.scheduler_adapter import RealSchedulerAdapter


def test_normalize_daily_cron_keeps_day_of_week_empty() -> None:
    assert RealSchedulerAdapter._normalize_cron("0 9 * * *") == "0 0 9 * * ?"


def test_normalize_weekday_range_to_scheduler_numbers() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("0 9 * * mon-fri")
        == "0 0 9 ? * 1-5"
    )


def test_normalize_weekday_list_to_scheduler_numbers() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("30 18 * * mon,wed,fri")
        == "0 30 18 ? * 1,3,5"
    )


def test_normalize_sunday_alias_to_scheduler_number() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("0 9 * * sun")
        == "0 0 9 ? * 7"
    )
