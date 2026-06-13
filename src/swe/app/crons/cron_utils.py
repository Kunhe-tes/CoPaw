# -*- coding: utf-8 -*-
"""cron 展示时间计算工具。
用于计算下一次运行时间（仅界面展示，不参与实际调度）。
外部调度平台才是定时触发来源。
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter


def compute_next_run_at(
    cron_expression: str,
    timezone_name: str,
    *,
    now: datetime | None = None,
) -> datetime:
    """计算下一次运行时间，仅用于界面展示。

    Args:
        cron_expression: 5字段 cron 表达式
        timezone_name: 时区名称 (如 "Asia/Shanghai")
        now: 计算基准时间，默认为当前时间

    Returns:
        下一次触发时间的 datetime 对象（带时区信息）
    """
    tz = ZoneInfo(timezone_name or "UTC")
    base = now or datetime.now(tz)
    if base.tzinfo is None:
        base = base.replace(tzinfo=tz)
    else:
        base = base.astimezone(tz)
    return croniter(cron_expression, base).get_next(datetime)


def compute_next_run_times(
    cron_expression: str,
    timezone_name: str,
    *,
    count: int = 3,
    now: datetime | None = None,
) -> list[datetime]:
    """计算后续多次运行时间，仅用于界面展示。"""
    if count <= 0:
        return []

    run_times: list[datetime] = []
    cursor = now
    for _ in range(count):
        next_run = compute_next_run_at(
            cron_expression,
            timezone_name,
            now=cursor,
        )
        run_times.append(next_run)
        cursor = next_run + timedelta(seconds=1)
    return run_times
