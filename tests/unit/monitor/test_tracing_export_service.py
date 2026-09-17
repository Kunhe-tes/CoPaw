# -*- coding: utf-8 -*-
"""Tests for tracing export service."""

from datetime import datetime
from unittest.mock import MagicMock

from monitor.app.models.tracing import UserMessageItem
from monitor.app.services.tracing.export_service import (
    TracingExportService,
    _EXPORT_MESSAGE_MAX_LENGTH,
    _EXPORT_MESSAGE_TRUNCATION_SUFFIX,
)


def _build_message(user_message: str) -> UserMessageItem:
    """构造导出测试使用的用户消息对象。"""
    return UserMessageItem(
        trace_id="trace-1",
        source_id="source-1",
        user_id="user-1",
        user_name="tester",
        bbk_id="100",
        session_id="session-1",
        channel="web",
        user_message=user_message,
        model_name="gpt-test",
        start_time=datetime(2026, 7, 9, 12, 0, 0),
        duration_ms=120,
    )


def test_build_export_row_keeps_short_message() -> None:
    """短消息导出时应保持原样。"""
    service = TracingExportService(MagicMock())

    row = service._build_export_row(_build_message("hello"))

    assert row[5] == "hello"


def test_build_export_row_truncates_overlong_message() -> None:
    """超长消息导出时应截断并追加省略标记。"""
    service = TracingExportService(MagicMock())
    original = "a" * (_EXPORT_MESSAGE_MAX_LENGTH + 100)

    row = service._build_export_row(_build_message(original))

    assert len(row[5]) == _EXPORT_MESSAGE_MAX_LENGTH
    assert row[5].endswith(_EXPORT_MESSAGE_TRUNCATION_SUFFIX)
    assert row[5] == (
        "a"
        * (_EXPORT_MESSAGE_MAX_LENGTH - len(_EXPORT_MESSAGE_TRUNCATION_SUFFIX))
        + _EXPORT_MESSAGE_TRUNCATION_SUFFIX
    )
