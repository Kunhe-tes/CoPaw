# -*- coding: utf-8 -*-
"""Exercise tracing transactions through the real database adapter."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiomysql.cursors import RE_INSERT_VALUES

from swe.database import DatabaseConfig, DatabaseConnection
from swe.tracing.config import TracingConfig
from swe.tracing.models import EventType, Span
from swe.tracing.store import TraceStore
from swe.tracing.writer import SpanWriter


def transactional_store():
    cursor = MagicMock()
    cursor.rowcount = 0  # An idempotent duplicate can affect zero rows.
    cursor.executemany = AsyncMock()
    connection = MagicMock()
    connection.begin = AsyncMock()
    connection.commit = AsyncMock()
    connection.rollback = AsyncMock()
    connection.cursor.return_value.__aenter__ = AsyncMock(return_value=cursor)

    @asynccontextmanager
    async def acquire():
        yield connection

    db = DatabaseConnection(DatabaseConfig())
    db._pool = MagicMock()
    db._pool.acquire = acquire
    store = TraceStore(TracingConfig(), db)
    spans = [
        Span(
            span_id="span",
            trace_id="trace",
            source_id="source",
            name="tool",
            event_type=EventType.TOOL_CALL_START,
            start_time=datetime.now(),
        ),
    ]
    return store, spans, connection, cursor


@pytest.mark.asyncio
async def test_zero_affected_rows_confirms_idempotent_batch_in_one_transaction():
    store, spans, connection, cursor = transactional_store()
    assert await store.batch_create_spans(spans) == 1
    connection.begin.assert_awaited_once()
    connection.commit.assert_awaited_once()
    connection.rollback.assert_not_awaited()
    query, _params = cursor.executemany.call_args.args
    assert "ON DUPLICATE KEY UPDATE" in query
    assert RE_INSERT_VALUES.match(query)


@pytest.mark.asyncio
async def test_driver_chunk_failure_rolls_back_batch():
    store, spans, connection, cursor = transactional_store()
    cursor.executemany.side_effect = OSError("second SQL chunk failed")
    with pytest.raises(OSError):
        await store.batch_create_spans(spans)
    connection.rollback.assert_awaited_once()
    connection.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_write_rolls_back_before_returning_connection():
    store, spans, connection, cursor = transactional_store()
    started = asyncio.Event()

    async def blocked(*_args):
        started.set()
        await asyncio.Event().wait()

    cursor.executemany.side_effect = blocked
    writing = asyncio.create_task(store.batch_create_spans(spans))
    await started.wait()
    writing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await writing
    connection.rollback.assert_awaited_once()
    connection.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_transaction_is_not_committed_by_span_batch():
    store, spans, connection, _cursor = transactional_store()
    async with store.db.transaction():
        await store.batch_create_spans(spans)
        connection.commit.assert_not_awaited()
        connection.begin.assert_awaited_once()
    connection.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_closed_connection_rollback_does_not_replace_cancellation():
    store, spans, connection, cursor = transactional_store()
    started = asyncio.Event()

    async def cancelled_transport(*_args):
        started.set()
        await asyncio.Event().wait()

    connection.rollback.side_effect = OSError("connection already closed")
    cursor.executemany.side_effect = cancelled_transport
    writing = asyncio.create_task(store.batch_create_spans(spans))
    await started.wait()
    writing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await writing


@pytest.mark.asyncio
async def test_shutdown_deadline_survives_cancelled_transport_rollback_error():
    store, spans, connection, cursor = transactional_store()
    started = asyncio.Event()

    async def cancelled_transport(*_args):
        started.set()
        await asyncio.Event().wait()

    connection.rollback.side_effect = OSError("connection already closed")
    cursor.executemany.side_effect = cancelled_transport
    writer = SpanWriter(TracingConfig(batch_size=1, shutdown_timeout=0.02))
    writer.start(store)
    await writer.submit(spans[0])
    await started.wait()
    closing = asyncio.create_task(writer.close())
    await asyncio.sleep(0.08)
    try:
        assert closing.done()
        assert writer.task.done()
        assert writer.pending
    finally:
        if not closing.done():
            connection.rollback.side_effect = None
            writer.task.cancel()
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await closing
