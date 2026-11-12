# -*- coding: utf-8 -*-
"""Write failures must not spread across entries or attachment lifecycles."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.tracing.config import TracingConfig
from swe.tracing.models import EventType, Span
from swe.tracing.writer import SpanWriter


def make_span(name, trace_id=None):
    return Span(
        span_id=name,
        trace_id=trace_id or name,
        source_id="source",
        name=name,
        event_type=EventType.TOOL_CALL_START,
        start_time=datetime.now(),
    )


async def drained(writer):
    async with writer._changed:
        await asyncio.wait_for(
            writer._changed.wait_for(lambda: not writer._entries),
            3,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["insert", "update", "mixed"])
async def test_bad_entry_does_not_discard_valid_batch_members(operation):
    store = MagicMock()
    persisted = set()
    calls = []

    async def insert(spans):
        calls.append(tuple(span.span_id for span in spans))
        if any(span.span_id == "bad" for span in spans):
            raise ValueError("malformed span")
        persisted.update(span.span_id for span in spans)
        return len(spans)

    async def update(span):
        calls.append((span.span_id,))
        if span.span_id == "bad":
            raise ValueError("malformed update")
        persisted.add(span.span_id)

    store.batch_create_spans = insert
    store.update_span = update
    writer = SpanWriter(TracingConfig(batch_size=100, flush_interval=60))
    writer.start(store)
    try:
        for name in ("good-before", "bad", "good-after"):
            writer.register_trace(name)
            await writer.submit(
                make_span(name),
                inserted=operation == "update"
                or (operation == "mixed" and name == "bad"),
            )
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await writer.flush()
        await drained(writer)
        assert persisted == {"good-before", "good-after"}
        assert writer.dropped_spans == 1
        assert calls.count(("bad",)) == 3
        for name in persisted:
            await writer.flush(name)
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await writer.flush("bad")
    finally:
        await writer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("release_before_confirmation", [False, True])
async def test_reattachment_shares_pending_external_writes(
    fails,
    release_before_confirmation,
):
    started = asyncio.Event()
    release_write = asyncio.Event()

    async def insert(spans):
        started.set()
        await release_write.wait()
        if fails:
            raise ValueError("malformed span")
        return len(spans)

    store = MagicMock()
    store.batch_create_spans = AsyncMock(side_effect=insert)
    writer = SpanWriter(TracingConfig(batch_size=1, flush_interval=60))
    writer.start(store)
    writer.register_trace("external", external=True)
    release_first = writer.attach_producer("external")
    state = writer._traces["external"]
    try:
        await writer.submit(make_span("old", "external"))
        await started.wait()
        release_first()
        writer.register_trace("external", external=True)
        release_second = writer.attach_producer("external")
        assert writer._traces["external"] is state
        barrier = asyncio.create_task(writer.flush("external"))
        await asyncio.sleep(0)
        if release_before_confirmation:
            release_second()
            assert writer.is_registered("external")
        release_write.set()
        await drained(writer)
        if fails:
            with pytest.raises(TimeoutError, match="unconfirmed"):
                await barrier
            with pytest.raises(TimeoutError, match="unconfirmed"):
                await writer.flush("external")
            with pytest.raises(RuntimeError, match="unconfirmed"):
                await writer.submit(make_span("new", "external"))
        else:
            await barrier
        if not release_before_confirmation:
            assert writer._traces["external"] is state
            if not fails:
                await writer.flush("external")
        release_second()
        release_second()  # Context release remains idempotent.
        assert not writer.is_registered("external")
    finally:
        release_write.set()
        await writer.close()
