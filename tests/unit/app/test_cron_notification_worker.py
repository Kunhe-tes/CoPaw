# -*- coding: utf-8 -*-
"""定时任务通知 worker 测试。"""

from datetime import datetime, timezone
from typing import Any

import pytest

from swe.app.crons.notification_worker import CronNotificationWorker


class _MonitorClient:
    def __init__(self) -> None:
        self.claim_payload: dict[str, Any] = {}

    async def claim_due_notifications(self, **kwargs):
        self.claim_payload = kwargs
        return []


@pytest.mark.asyncio
async def test_scan_once_passes_configured_source_ids(monkeypatch):
    """领取通知时必须携带当前实例允许处理的 source 范围。"""
    monkeypatch.setenv(
        "SWE_CRON_NOTIFICATION_SOURCE_IDS",
        "source-a, source-b\nsource-a",
    )
    monitor_client = _MonitorClient()
    worker = CronNotificationWorker(
        multi_agent_manager=object(),
        monitor_client=monitor_client,
        batch_size=5,
    )
    worker._now_utc = lambda: datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)

    await worker.scan_once()

    assert monitor_client.claim_payload["source_ids"] == [
        "source-a",
        "source-b",
    ]
