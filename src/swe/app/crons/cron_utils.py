# -*- coding: utf-8 -*-
"""cron 展示时间计算工具。
用于计算下一次运行时间（仅界面展示，不参与实际调度）。
外部调度平台才是定时触发来源。
"""

import calendar
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter


_NEAREST_WEEKDAY_DOM_RE = re.compile(
    r"^(?P<day>[1-9]|[12][0-9]|3[01])W$",
    re.IGNORECASE,
)


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
    try:
        return croniter(cron_expression, base).get_next(datetime)
    except Exception:
        fallback = _compute_nearest_weekday_next_run(cron_expression, base)
        if fallback is not None:
            return fallback
        raise


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


def _compute_nearest_weekday_next_run(
    cron_expression: str,
    base: datetime,
) -> datetime | None:
    parts = [part for part in cron_expression.split() if part]
    if len(parts) == 5:
        second_expr = "0"
        minute_expr, hour_expr, day_of_month_expr, month_expr, day_of_week_expr = parts
    elif len(parts) == 6:
        (
            second_expr,
            minute_expr,
            hour_expr,
            day_of_month_expr,
            month_expr,
            day_of_week_expr,
        ) = parts
    else:
        return None

    match = _NEAREST_WEEKDAY_DOM_RE.match(day_of_month_expr)
    if not match:
        return None
    if day_of_week_expr not in {"*", "?"}:
        return None

    second = _parse_single_number(second_expr, 0, 59)
    minute = _parse_single_number(minute_expr, 0, 59)
    hour = _parse_single_number(hour_expr, 0, 23)
    if second is None or minute is None or hour is None:
        return None

    target_day = int(match.group("day"))
    for month_offset in range(0, 120):
        month_index = base.month - 1 + month_offset
        year = base.year + month_index // 12
        month = month_index % 12 + 1
        if not _field_matches_number(month_expr, month, 1, 12):
            continue

        day = _nearest_weekday_in_month(year, month, target_day)
        candidate = datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            tzinfo=base.tzinfo,
        )
        if candidate > base:
            return candidate

    return None


def _parse_single_number(value: str, minimum: int, maximum: int) -> int | None:
    if not value.isdigit():
        return None
    parsed = int(value)
    if parsed < minimum or parsed > maximum:
        return None
    return parsed


def _field_matches_number(
    expression: str,
    value: int,
    minimum: int,
    maximum: int,
) -> bool:
    if expression == "*":
        return True

    for segment in expression.split(","):
        if "-" in segment:
            start_text, end_text = segment.split("-", 1)
            start = _parse_single_number(start_text, minimum, maximum)
            end = _parse_single_number(end_text, minimum, maximum)
            if start is None or end is None or start > end:
                return False
            if start <= value <= end:
                return True
            continue

        parsed = _parse_single_number(segment, minimum, maximum)
        if parsed is None:
            return False
        if parsed == value:
            return True

    return False


def _nearest_weekday_in_month(year: int, month: int, target_day: int) -> int:
    last_day = calendar.monthrange(year, month)[1]
    day = min(target_day, last_day)
    weekday = datetime(year, month, day).weekday()

    if weekday == 5:
        if day == 1:
            return 3
        return day - 1

    if weekday == 6:
        if day == last_day:
            return day - 2
        return day + 1

    return day
