# -*- coding: utf-8 -*-
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from monitor.app.services.cron.batch_status_report import (
    collect,
    report_window,
    reportable,
)


@pytest.mark.asyncio
async def test_snapshot_uses_placeholder_for_unnamed_task():
    reader = AsyncMock()
    reader.fetch_all.side_effect = [
        [
            {
                "batch_id": "internal-batch-id",
                "job_id": "internal-job-id",
                "job_name": None,
                "logical_fire_at": datetime(2026, 11, 24, 3),
                "status": "unavailable",
            },
        ],
        [],
        [],
        [],
    ]
    snapshot = await collect(
        reader,
        "S",
        date(2026, 11, 24),
        datetime(2026, 11, 24, 4, tzinfo=timezone.utc),
    )
    (batch,) = snapshot["batches"]
    assert batch["batch_id"] == "internal-batch-id"
    assert batch["name"] == "未命名任务"


def test_business_window_preserves_original_day():
    now = datetime(2026, 11, 25, 1, tzinfo=timezone.utc)
    assert report_window(date(2026, 11, 24), now) == (
        datetime(2026, 11, 23, 16),
        datetime(2026, 11, 24, 16),
        now.replace(tzinfo=None),
    )


def test_only_skipped_batches_are_filtered():
    assert not reportable(
        {"status": "received", "member_count": 0, "runtime_skipped_count": 0},
    )
    assert not reportable(
        {"status": "completed", "member_count": 2, "runtime_skipped_count": 2},
    )
    assert reportable(
        {"status": "failed", "member_count": 2, "runtime_skipped_count": 1},
    )
    assert reportable(
        {"status": "completed", "member_count": 2, "runtime_skipped_count": 0},
    )
    assert reportable(
        {
            "status": "unavailable",
            "member_count": 0,
            "runtime_skipped_count": 0,
        },
    )
