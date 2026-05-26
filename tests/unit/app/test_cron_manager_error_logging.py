# -*- coding: utf-8 -*-
"""CronManager 错误日志回归测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from swe.app.crons.manager import CronManager
from swe.app.crons.models import CronJobState


def test_handle_execution_error_logs_exception_traceback(monkeypatch):
    """执行失败日志必须携带原始异常堆栈，便于定位生产问题。"""
    manager = CronManager(
        repo=object(),
        runner=object(),
        channel_manager=object(),
    )
    actual_time = datetime.now(timezone.utc)
    manager._record_failure_timing = (  # pylint: disable=protected-access
        lambda _st, _actual_time, _status, _message: (actual_time, 0)
    )

    def _raise_error():
        raise RuntimeError("boom")

    try:
        _raise_error()
    except RuntimeError as exc:
        error = exc

    captured: dict[str, object] = {}

    def fake_warning(message, *args, **kwargs):
        captured["message"] = message
        captured["args"] = args
        captured["exc_info"] = kwargs.get("exc_info")

    monkeypatch.setattr(
        "swe.app.crons.manager.logger.warning",
        fake_warning,
    )

    result = (
        manager._handle_execution_error(  # pylint: disable=protected-access
            CronJobState(),
            actual_time,
            error,
        )
    )

    assert captured["exc_info"] == (
        type(error),
        error,
        error.__traceback__,
    )
    assert result == ("error", "boom", actual_time, 0)
