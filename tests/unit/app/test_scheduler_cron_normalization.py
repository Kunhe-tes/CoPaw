# -*- coding: utf-8 -*-
"""外部调度平台 cron 表达式转换规则测试。"""

from swe.app.crons.scheduler_adapter import RealSchedulerAdapter


def test_normalize_daily_cron_keeps_day_of_week_empty() -> None:
    assert RealSchedulerAdapter._normalize_cron("0 9 * * *") == "0 0 9 * * ?"


def test_normalize_weekday_range_to_scheduler_numbers() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("0 9 * * mon-fri")
        == "0 0 9 ? * 2-6"
    )


def test_normalize_numeric_weekday_range_to_scheduler_numbers() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("0 9 * * 1-5")
        == "0 0 9 ? * 2-6"
    )


def test_normalize_full_numeric_weekday_range_wraps_sunday() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("0 9 * * 1-7")
        == "0 0 9 ? * 2,3,4,5,6,7,1"
    )


def test_normalize_weekday_range_containing_sunday_to_list() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("0 9 * * fri-sun")
        == "0 0 9 ? * 6,7,1"
    )


def test_normalize_weekday_list_to_scheduler_numbers() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("30 18 * * mon,wed,fri")
        == "0 30 18 ? * 2,4,6"
    )


def test_normalize_sunday_alias_to_scheduler_number() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("0 9 * * sun")
        == "0 0 9 ? * 1"
    )


def test_normalize_numeric_sunday_aliases_to_scheduler_number() -> None:
    assert RealSchedulerAdapter._normalize_cron("0 9 * * 0") == "0 0 9 ? * 1"
    assert RealSchedulerAdapter._normalize_cron("0 9 * * 7") == "0 0 9 ? * 1"


def test_normalize_saturday_to_scheduler_number() -> None:
    assert (
        RealSchedulerAdapter._normalize_cron("0 9 * * sat")
        == "0 0 9 ? * 7"
    )
