# -*- coding: utf-8 -*-
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.tracing.config import TracingConfig
from swe.tracing.models import EventType, Span
from swe.tracing.store import TraceStore


@pytest.mark.asyncio
async def test_span_batch_uses_lazy_prepared_rows_and_writer_budgets():
    db = MagicMock()
    seen = []

    async def insert(template, rows, **limits):
        assert not isinstance(rows, list)
        assert template.columns == 23
        assert "ON DUPLICATE KEY UPDATE" in template.suffix
        assert limits == {"max_rows": 2, "max_bytes": 4096}
        seen.extend(rows)
        return len(seen)

    db.insert_prepared = AsyncMock(side_effect=insert)
    store = TraceStore(TracingConfig(batch_size=2, max_batch_bytes=4096), db)
    span = Span(
        span_id="span",
        trace_id="trace",
        source_id="tenant",
        name="tool",
        event_type=EventType.TOOL_CALL_START,
        start_time=datetime(2026, 10, 16),
        tool_input={"中文": "😀\\\x00"},
    )
    assert await store.batch_create_spans([span]) == 1
    assert seen[0][2] == "tenant"
    assert seen[0][18] == '{"\\u4e2d\\u6587": "\\ud83d\\ude00\\\\\\u0000"}'
    db.execute_many.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    ["tool", "名" * 256, "名" * 256 + "尾"],
    ids=["short", "at-limit", "over-limit"],
)
async def test_span_inserts_limit_name_to_256_characters(name):
    db = MagicMock()
    db.execute = AsyncMock()

    async def insert(template, rows, **limits):
        (row,) = rows
        assert row[3] == name[:256]
        return 1

    db.insert_prepared = AsyncMock(side_effect=insert)
    store = TraceStore(TracingConfig(), db)
    span = Span(
        span_id="span",
        trace_id="trace",
        source_id="tenant",
        name=name,
        event_type=EventType.TOOL_CALL_START,
        start_time=datetime(2026, 10, 16),
    )

    await store.create_span(span)
    assert db.execute.await_args.args[1][3] == name[:256]
    assert await store.batch_create_spans([span]) == 1
    assert span.name == name


@pytest.mark.asyncio
async def test_empty_or_disconnected_span_batches_do_not_claim_confirmation():
    store = TraceStore(TracingConfig(), None)
    assert await store.batch_create_spans([]) == 0
