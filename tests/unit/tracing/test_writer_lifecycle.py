# -*- coding: utf-8 -*-
"""Deterministic regression coverage for confirmed tracing writes."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.tracing.config import TracingConfig
from swe.tracing.manager import (
    TraceManager,
    get_current_trace,
    set_current_trace,
)
from swe.tracing.models import EventType


class GatedDatabase:
    """Hold real store writes at the database boundary."""

    is_connected = True

    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.rows = []
        self.batches = []
        self.updates = []
        self.trace_completed = asyncio.Event()
        self.fail_updates = False

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def insert_prepared(self, _query, params, **_limits):
        params = list(params)
        self.batches.append(list(params))
        self.rows.extend(params)
        self.started.set()
        await self.release.wait()
        return len(params)

    async def execute(self, query, params=None):
        if "UPDATE swe_tracing_traces SET" in query:
            self.trace_completed.set()
        if "UPDATE swe_tracing_spans SET" in query:
            if self.fail_updates:
                raise OSError("update unavailable")
            self.updates.append(params)
        return 1

    async def fetch_one(self, _query, _params=None):
        return None

    async def fetch_all(self, _query, _params=None):
        return []


async def new_manager(**options):
    db = GatedDatabase()
    config = TracingConfig(
        enabled=True,
        retention_days=0,
        flush_interval=60,
        **options,
    )
    manager = TraceManager(config, db)
    await manager.initialize()
    trace_id = await manager.start_trace(
        "user",
        "session",
        "console",
        "source",
    )
    return manager, db, trace_id


async def emit(manager, trace_id, **kwargs):
    return await manager.emit_span(
        trace_id,
        EventType.TOOL_CALL_START,
        "tool",
        "source",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_end_trace_waits_for_inflight_insert():
    manager, db, trace_id = await new_manager(batch_size=1)
    producer = asyncio.create_task(emit(manager, trace_id))
    await db.started.wait()
    ending = asyncio.create_task(manager.end_trace(trace_id))
    await asyncio.sleep(0.02)
    try:
        assert not db.trace_completed.is_set()
        assert not ending.done()
    finally:
        db.release.set()
        await producer
        await ending
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_close_drains_inflight_without_cancelling_it():
    manager, db, trace_id = await new_manager(batch_size=100)
    await emit(manager, trace_id)
    flush = asyncio.create_task(manager._flush_spans())
    await db.started.wait()
    closing = asyncio.create_task(manager.close())
    await asyncio.sleep(0.02)
    try:
        assert not closing.done()
    finally:
        db.release.set()
        await flush
        await closing
        set_current_trace(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("flush_before_drop", [False, True])
async def test_permanently_failed_span_is_dropped_after_three_attempts(
    flush_before_drop,
):
    manager, db, trace_id = await new_manager(batch_size=1)
    db.release.set()
    db.insert_prepared = AsyncMock(side_effect=OSError("database unavailable"))
    try:
        await emit(manager, trace_id)
        ending = (
            asyncio.create_task(manager.end_trace(trace_id))
            if flush_before_drop
            else None
        )

        async def wait_until_dropped():
            async with manager._writer._changed:
                await manager._writer._changed.wait_for(
                    lambda: not manager._writer._entries,
                )

        await asyncio.wait_for(wait_until_dropped(), timeout=2)
        assert db.insert_prepared.await_count == 3
        assert not manager._writer.pending
        assert not manager._writer.queue
        assert manager._writer._bytes == 0
        with pytest.raises(TimeoutError, match="unconfirmed"):
            if ending is not None:
                await asyncio.wait_for(ending, timeout=1)
            else:
                await manager.end_trace(trace_id)
        # Unknown historical targets fail; a fresh global barrier has no old targets.
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await manager._writer.flush(trace_id)
        await manager._writer.flush()
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await manager._writer.flush("unrelated-trace")
        assert not db.trace_completed.is_set()
        assert trace_id not in manager._active_traces
        if not flush_before_drop:
            assert get_current_trace() is None
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_count", [1, 5])
async def test_failure_history_is_bounded_and_recovery_preserves_confirmation(
    failure_count,
    monkeypatch,
):
    monkeypatch.setattr("swe.tracing.writer._MAX_WRITE_ATTEMPTS", 1)
    manager, db, trace_id = await new_manager(batch_size=1, max_queue_spans=2)
    db.release.set()
    original_insert = db.insert_prepared
    db.insert_prepared = AsyncMock(side_effect=OSError("database unavailable"))
    failed_trace_ids = []
    try:
        for index in range(failure_count):
            if index:
                trace_id = await manager.start_trace(
                    "user",
                    "session",
                    "console",
                    "source",
                )
            failed_trace_ids.append(trace_id)
            await emit(manager, trace_id)
            with pytest.raises(TimeoutError, match="unconfirmed"):
                await manager.end_trace(trace_id)
            async with manager._writer._changed:
                await asyncio.wait_for(
                    manager._writer._changed.wait_for(
                        lambda: not manager._writer._entries,
                    ),
                    timeout=5,
                )
            assert not manager._active_traces
            assert get_current_trace() is None
            assert len(manager._writer._traces) <= 2
            assert not manager._writer.pending
        assert not db.trace_completed.is_set()
        assert not manager._writer._traces
        for failed_id in failed_trace_ids:
            with pytest.raises(TimeoutError, match="unconfirmed"):
                await manager._writer.flush(failed_id)

        db.insert_prepared = original_insert
        recovered_id = await manager.start_trace(
            "user",
            "session",
            "console",
            "source",
        )
        await emit(manager, recovered_id)
        await manager.end_trace(recovered_id)
        assert db.trace_completed.is_set()
        assert not manager._writer._traces
        assert not manager._active_traces
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [OSError("store unavailable"), asyncio.CancelledError()],
)
async def test_end_trace_releases_state_when_final_update_fails(failure):
    manager, db, trace_id = await new_manager()
    manager.store.update_trace = AsyncMock(side_effect=failure)
    try:
        with pytest.raises(type(failure)):
            await manager.end_trace(trace_id)
        assert trace_id not in manager._active_traces
        assert get_current_trace() is None
        assert not db.trace_completed.is_set()
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_update_during_insert_is_confirmed_before_trace_end():
    manager, db, trace_id = await new_manager(batch_size=100)
    span_id = await emit(manager, trace_id)
    flush = asyncio.create_task(manager._flush_spans())
    await db.started.wait()
    await manager.update_span(span_id, trace_id, tool_output="finished")
    ending = asyncio.create_task(manager.end_trace(trace_id))
    await asyncio.sleep(0.02)
    try:
        assert not ending.done()
    finally:
        db.release.set()
        await flush
        await ending
        await manager.close()
        set_current_trace(None)
    assert len(db.updates) == 1
    assert db.updates[0][4] == "finished"
    assert isinstance(db.updates[0][0], datetime)


@pytest.mark.asyncio
async def test_emit_signals_writer_without_waiting_for_database():
    manager, db, trace_id = await new_manager(batch_size=1)
    producer = asyncio.create_task(emit(manager, trace_id))
    await db.started.wait()
    try:
        await asyncio.wait_for(asyncio.shield(producer), 0.05)
    finally:
        db.release.set()
        await producer
        await manager.close()


@pytest.mark.asyncio
async def test_close_caller_cancellation_does_not_cancel_drain():
    manager, db, trace_id = await new_manager(batch_size=100)
    await emit(manager, trace_id)
    closing = asyncio.create_task(manager.close())
    await db.started.wait()
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    db.release.set()
    await manager.close()
    assert not manager._pending_spans


@pytest.mark.asyncio
async def test_failed_update_keeps_trace_unconfirmed():
    manager, db, trace_id = await new_manager(write_timeout=0.04)
    span_id = await emit(manager, trace_id)
    flushing = asyncio.create_task(manager._flush_spans())
    await db.started.wait()
    await manager.update_span(span_id, trace_id, tool_output="finished")
    db.fail_updates = True
    db.release.set()
    try:
        with pytest.raises(TimeoutError):
            await manager.end_trace(trace_id)
        assert not db.trace_completed.is_set()
        assert trace_id not in manager._active_traces
        assert span_id in manager._pending_spans
    finally:
        await flushing
        db.fail_updates = False
        await manager.close()


@pytest.mark.asyncio
async def test_shutdown_deadline_reports_unconfirmed_work():
    manager, db, trace_id = await new_manager(shutdown_timeout=0.03)
    await emit(manager, trace_id)
    with pytest.raises(TimeoutError, match="unconfirmed"):
        await manager.close()
    assert manager._pending_spans
    assert manager._flush_task is None
    assert not db.trace_completed.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("close_manager", [False, True])
async def test_shutdown_returns_when_writer_cancellation_cleanup_stalls(
    close_manager,
):
    manager, db, trace_id = await new_manager(
        batch_size=1,
        shutdown_timeout=0.02,
    )
    cancelling = asyncio.Event()
    release_cleanup = asyncio.Event()
    store_closed = asyncio.Event()
    manager.store.close = AsyncMock(side_effect=store_closed.set)

    async def stalled_cleanup(_query, _params, **_limits):
        db.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelling.set()
            await release_cleanup.wait()
            raise

    db.insert_prepared = stalled_cleanup
    await emit(manager, trace_id)
    await db.started.wait()
    close = manager.close if close_manager else manager._writer.close
    closing = asyncio.create_task(close())
    await cancelling.wait()
    try:
        done, _ = await asyncio.wait({closing}, timeout=0.2)
        assert done, "shutdown waited indefinitely for cancellation cleanup"
        with pytest.raises(
            TimeoutError,
            match="unconfirmed.*writer still running",
        ):
            await closing
        assert not manager._writer.task.done()
        assert manager._pending_spans
        assert not store_closed.is_set()
    finally:
        release_cleanup.set()
        await asyncio.gather(manager._writer.task, return_exceptions=True)
        await asyncio.gather(closing, return_exceptions=True)
        if close_manager:
            await asyncio.wait_for(store_closed.wait(), 0.2)
        else:
            await asyncio.gather(manager.close(), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_manager", [False, True])
async def test_shutdown_logs_cleanup_failure_during_cancellation_grace(
    monkeypatch,
    close_manager,
):
    from swe.tracing.writer import SpanWriter

    started = asyncio.Event()
    failure = OSError("writer cancellation cleanup failed")
    log = MagicMock()

    async def failing_cleanup(_self):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise failure

    monkeypatch.setattr(SpanWriter, "_run", failing_cleanup)
    monkeypatch.setattr("swe.tracing.writer.logger", log)
    manager, _db, trace_id = await new_manager(shutdown_timeout=0.02)
    manager.store.close = AsyncMock()
    await emit(manager, trace_id)
    await started.wait()
    close = manager.close if close_manager else manager._writer.close
    try:
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await close()
        assert manager._writer.task.done()
        assert manager._pending_spans
        failures = [
            call.kwargs["exc_info"]
            for call in log.error.call_args_list
            if "exc_info" in call.kwargs
        ]
        assert len(failures) == 1
        assert failures[0][0] is OSError
        assert failures[0][1] is failure
        assert failures[0][2] is failure.__traceback__
        if close_manager:
            manager.store.close.assert_awaited_once()
    finally:
        await asyncio.gather(manager.close(), return_exceptions=True)
        await asyncio.gather(manager._writer.task, return_exceptions=True)


@pytest.mark.asyncio
async def test_batches_are_limited_by_rows():
    manager, db, trace_id = await new_manager(batch_size=2)
    db.release.set()
    for _ in range(7):
        await emit(manager, trace_id)
    await manager.close()
    assert [len(batch) for batch in db.batches] == [2, 2, 2, 1]


@pytest.mark.asyncio
async def test_batches_are_limited_by_estimated_bytes():
    manager, db, trace_id = await new_manager(max_batch_bytes=5000)
    db.release.set()
    for _ in range(3):
        await emit(manager, trace_id, tool_input={"text": "x" * 200})
    await manager.close()
    assert [len(batch) for batch in db.batches] == [1, 1, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limits",
    [{"max_queue_spans": 1}, {"max_queue_bytes": 5000}],
)
async def test_inflight_work_counts_toward_backpressure(limits):
    manager, db, trace_id = await new_manager(batch_size=100, **limits)
    await emit(manager, trace_id, tool_input={"text": "x" * 200})
    producer = asyncio.create_task(
        emit(manager, trace_id, tool_input={"text": "x" * 200}),
    )
    await db.started.wait()
    try:
        await asyncio.sleep(0.02)
        assert not producer.done()
    finally:
        db.release.set()
        await producer
        await manager.close()


@pytest.mark.asyncio
async def test_cancelled_flush_waiter_does_not_cancel_writer():
    manager, db, trace_id = await new_manager()
    await emit(manager, trace_id)
    flushing = asyncio.create_task(manager._flush_spans())
    await db.started.wait()
    flushing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await flushing
    db.release.set()
    await manager.close()
    assert not manager._pending_spans


@pytest.mark.asyncio
async def test_oversized_span_is_written_alone_without_truncation():
    manager, db, trace_id = await new_manager(
        max_queue_bytes=1000,
        max_batch_bytes=1000,
        sanitize_output=False,
    )
    db.release.set()
    await emit(manager, trace_id, tool_input={"text": "x" * 2000})
    await manager.close()
    assert len(db.batches) == 1
    assert "x" * 2000 in db.batches[0][0][18]


@pytest.mark.asyncio
async def test_non_bmp_json_escaping_counts_toward_byte_limit():
    manager, db, trace_id = await new_manager(sanitize_output=False)
    db.release.set()
    for _ in range(2):
        await emit(manager, trace_id, tool_input={"text": "😀" * 10000})
    await manager.close()
    assert [len(batch) for batch in db.batches] == [1, 1]


@pytest.mark.asyncio
async def test_snapshot_failure_rejects_admission_without_retaining_data():
    class Input:
        fail = True

        def __deepcopy__(self, _memo):
            if self.fail:
                raise RuntimeError("snapshot unavailable")
            return "safe value"

    manager, db, trace_id = await new_manager(
        batch_size=1,
        sanitize_output=False,
    )
    db.release.set()
    try:
        with pytest.raises(RuntimeError, match="snapshot unavailable"):
            await emit(manager, trace_id, tool_input={"value": Input()})
        assert not manager._pending_spans
    finally:
        Input.fail = False
        await manager.close()


@pytest.mark.asyncio
async def test_task_creation_supports_python310_signature(monkeypatch):
    create_task = asyncio.create_task

    def python310_create_task(coro, *, name=None):
        return create_task(coro, name=name)

    monkeypatch.setattr(asyncio, "create_task", python310_create_task)
    manager, db, trace_id = await new_manager()
    db.release.set()
    await emit(manager, trace_id)
    await manager.close()


@pytest.mark.asyncio
async def test_admission_freezes_input_before_caller_mutation():
    manager, db, trace_id = await new_manager(sanitize_output=False)
    payload = {"items": [["original"]]}
    await emit(manager, trace_id, tool_input=payload)
    payload["items"][0][0] = "changed" * 10000
    db.release.set()
    await manager.close()
    assert '"original"' in db.rows[0][18]
    assert "changed" not in db.rows[0][18]


@pytest.mark.asyncio
async def test_failed_insert_retries_latest_version_with_stable_identity():
    manager, db, trace_id = await new_manager(batch_size=1)
    original = db.insert_prepared
    failed = False

    async def unknown_commit(query, params, **limits):
        nonlocal failed
        count = await original(query, params, **limits)
        if not failed:
            failed = True
            raise OSError("commit acknowledgement lost")
        return count

    db.insert_prepared = unknown_commit
    span_id = await emit(manager, trace_id)
    await db.started.wait()
    await manager.update_span(span_id, trace_id, tool_output="finished")
    db.release.set()
    await manager.end_trace(trace_id)
    await manager.close()
    assert len(db.rows) == 2
    assert all(row[0] == span_id for row in db.rows)
    assert db.rows[-1][19] == "finished"


@pytest.mark.asyncio
async def test_close_rejects_waiting_admission_without_cancelling_inflight():
    manager, db, trace_id = await new_manager(max_queue_spans=1)
    await emit(manager, trace_id)
    blocked = asyncio.create_task(emit(manager, trace_id))
    await db.started.wait()
    closing = asyncio.create_task(manager.close())
    try:
        with pytest.raises(RuntimeError, match="closing"):
            await asyncio.wait_for(blocked, 0.1)
    finally:
        db.release.set()
        await closing
    assert len(db.rows) == 1


@pytest.mark.asyncio
async def test_writer_does_not_inherit_request_transaction_or_trace():
    from swe.database.connection import _CURRENT_CONNECTION
    from swe.tracing.manager import TraceContext, get_current_trace

    db = GatedDatabase()
    observed = []
    original = db.insert_prepared

    async def check_context(query, params, **limits):
        observed.append((_CURRENT_CONNECTION.get(), get_current_trace()))
        return await original(query, params, **limits)

    db.insert_prepared = check_context
    manager = TraceManager(
        TracingConfig(enabled=True, retention_days=0),
        db,
    )
    token = _CURRENT_CONNECTION.set(object())
    set_current_trace(TraceContext("old", "u", "s", "c", "source"))
    try:
        await manager.initialize()
    finally:
        _CURRENT_CONNECTION.reset(token)
        set_current_trace(None)
    db.release.set()
    manager._writer.register_trace("trace")
    await emit(manager, "trace")
    await manager.close()
    assert observed == [(None, None)]


@pytest.mark.parametrize(
    "field",
    [
        "batch_size",
        "flush_interval",
        "max_batch_bytes",
        "max_queue_spans",
        "max_queue_bytes",
        "write_timeout",
        "shutdown_timeout",
    ],
)
def test_writer_limits_must_be_positive(field):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TracingConfig(**{field: 0})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage",
    ["flush_timeout", "update_error", "cancel_flush", "cancel_update"],
)
async def test_finalization_retry_preserves_all_aggregates(stage):
    manager, db, trace_id = await new_manager(batch_size=100)
    db.release.set()
    stale_trace = manager._active_traces[trace_id].model_copy(deep=True)
    manager.store.get_trace = AsyncMock(return_value=stale_trace)
    span_id = await emit(
        manager,
        trace_id,
        model_name="model-a",
        input_tokens=12,
        tool_name="tool-a",
        skill_name="skill-a",
    )
    await manager.update_span(span_id, trace_id, output_tokens=7)
    flush = manager._writer.flush
    update = manager.store.update_trace
    started = asyncio.Event()

    async def blocked(*_args):
        started.set()
        await asyncio.Event().wait()

    if stage == "flush_timeout":
        manager._writer.flush = AsyncMock(
            side_effect=TimeoutError("unconfirmed"),
        )
    elif stage == "update_error":
        manager.store.update_trace = AsyncMock(
            side_effect=OSError("unavailable"),
        )
    elif stage == "cancel_flush":
        manager._writer.flush = blocked
    else:
        manager.store.update_trace = blocked
    try:
        if stage.startswith("cancel"):
            ending = asyncio.create_task(manager.end_trace(trace_id))
            await asyncio.wait_for(started.wait(), 1)
            ending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await ending
        else:
            with pytest.raises((TimeoutError, OSError)):
                await manager.end_trace(trace_id)
        assert trace_id not in manager._active_traces
        assert trace_id in manager._pending_finalizations
        assert not manager._finalizing_traces
        manager._writer.flush = flush
        manager.store.update_trace = AsyncMock(wraps=update)
        # Late accepted updates must still contribute to the retained snapshot.
        await emit(
            manager,
            trace_id,
            model_name="model-b",
            input_tokens=3,
            tool_name="tool-b",
            skill_name="skill-b",
        )
        await manager.end_trace(trace_id)
        written = manager.store.update_trace.call_args.args[0]
        assert written.total_input_tokens == 15
        assert written.total_output_tokens == 7
        assert written.model_name == "model-a"
        assert written.tools_used == ["tool-a", "tool-b"]
        assert written.skills_used == ["skill-a", "skill-b"]
        manager.store.get_trace.assert_not_awaited()
        assert trace_id not in manager._pending_finalizations
        assert manager._finalization_bytes == 0
        assert db.trace_completed.is_set()
    finally:
        manager._writer.flush = flush
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_count", [3, 5])
async def test_finalization_snapshot_eviction_cannot_complete_stale_trace(
    failure_count,
):
    manager, db, first_id = await new_manager(max_queue_spans=2)
    db.release.set()
    update = manager.store.update_trace
    manager.store.update_trace = AsyncMock(side_effect=OSError("unavailable"))
    ids = []
    try:
        for index in range(failure_count):
            trace_id = (
                first_id
                if index == 0
                else await manager.start_trace(
                    "user",
                    "session",
                    "console",
                    "source",
                )
            )
            ids.append(trace_id)
            await emit(manager, trace_id, input_tokens=index + 1)
            with pytest.raises(OSError):
                await manager.end_trace(trace_id)
            assert len(manager._pending_finalizations) <= 2
            assert (
                manager._finalization_bytes <= manager.config.max_queue_bytes
            )
            assert not manager._active_traces
        manager.store.update_trace = AsyncMock(wraps=update)
        # Failure history overflow must still reject every evicted snapshot.
        for trace_id in ids[:-2]:
            with pytest.raises(TimeoutError, match="unconfirmed"):
                await manager.end_trace(trace_id)
        manager.store.update_trace.assert_not_awaited()
        assert not db.trace_completed.is_set()
        await manager.end_trace(ids[-1])
        written = manager.store.update_trace.call_args.args[0]
        assert written.total_input_tokens == failure_count
        assert ids[-1] not in manager._pending_finalizations
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_oversized_finalization_is_invalidated_instead_of_retained():
    manager, db, trace_id = await new_manager(max_queue_bytes=1024)
    manager.store.update_trace = AsyncMock(side_effect=OSError("unavailable"))
    try:
        with pytest.raises(OSError):
            await manager.end_trace(trace_id)
        assert not manager._pending_finalizations
        assert manager._finalization_bytes == 0
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await manager.end_trace(trace_id)
        assert manager.store.update_trace.await_count == 1
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_concurrent_finalization_cannot_write_a_stale_fallback():
    manager, db, trace_id = await new_manager(batch_size=1)
    await emit(manager, trace_id, input_tokens=12)
    await db.started.wait()
    ending = asyncio.create_task(manager.end_trace(trace_id))
    await asyncio.sleep(0)
    try:
        with pytest.raises(RuntimeError, match="already in progress"):
            await manager.end_trace(trace_id)
        with pytest.raises(RuntimeError, match="sealed"):
            await emit(manager, trace_id, input_tokens=100)
        db.release.set()
        await ending
        assert not any(
            state.sealed for state in manager._writer._traces.values()
        )
        assert not manager._finalizing_traces
        assert not manager._active_traces
    finally:
        db.release.set()
        await ending
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_retry_keeps_terminal_intent_and_does_not_rewrite_completed_trace():
    from swe.tracing.models import TraceStatus

    manager, db, trace_id = await new_manager()
    update = manager.store.update_trace
    manager.store.update_trace = AsyncMock(side_effect=OSError("unavailable"))
    try:
        with pytest.raises(OSError):
            await manager.end_trace(
                trace_id,
                TraceStatus.ERROR,
                "model failed",
            )
        snapshot = manager._pending_finalizations[trace_id][0]
        manager.store.update_trace = AsyncMock(wraps=update)
        await manager.end_trace(trace_id)
        written = manager.store.update_trace.call_args.args[0]
        assert written.status == TraceStatus.ERROR
        assert written.error == "model failed"
        assert written.end_time == snapshot.end_time
        manager.store.get_trace = AsyncMock(return_value=written)
        await manager.end_trace(trace_id)
        assert manager.store.update_trace.await_count == 1
        assert not manager._pending_finalizations
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_running_database_record_cannot_replace_missing_local_aggregates():
    manager, db, trace_id = await new_manager()
    stale = manager._active_traces.pop(trace_id)
    manager.store.get_trace = AsyncMock(return_value=stale)
    manager.store.update_trace = AsyncMock()
    try:
        with pytest.raises(TimeoutError, match="aggregates are unavailable"):
            await manager.end_trace(trace_id)
        manager.store.update_trace.assert_not_awaited()
        assert not manager._active_traces
        assert not manager._pending_finalizations
        assert manager._writer.has_failed(trace_id)
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_lost_skill_finalization_cannot_mark_trace_complete(cancelled):
    manager, db, trace_id = await new_manager()
    detector = MagicMock()
    detector.on_reasoning_end = AsyncMock(
        side_effect=(
            asyncio.CancelledError() if cancelled else OSError("skill failed")
        ),
    )
    get_current_trace().skill_detector = detector
    try:
        with pytest.raises(
            asyncio.CancelledError if cancelled else TimeoutError,
        ):
            await manager.end_trace(trace_id)
        assert not manager._active_traces
        assert not manager._pending_finalizations
        assert get_current_trace() is None
        assert not db.trace_completed.is_set()
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await manager.end_trace(trace_id)
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_global_barrier_keeps_failed_target_but_later_barrier_recovers(
    monkeypatch,
):
    monkeypatch.setattr("swe.tracing.writer._MAX_WRITE_ATTEMPTS", 1)
    manager, db, trace_id = await new_manager(batch_size=1)
    original = db.insert_prepared
    fail = asyncio.Event()

    async def failing(*_args, **_kwargs):
        db.started.set()
        await fail.wait()
        raise OSError("database unavailable")

    db.insert_prepared = failing
    await emit(manager, trace_id)
    await db.started.wait()
    barrier = asyncio.create_task(manager._writer.flush())
    await asyncio.sleep(0)
    try:
        fail.set()
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await barrier
        assert not manager._writer._traces
        with pytest.raises(TimeoutError):
            await manager.end_trace(trace_id)
        with pytest.raises(RuntimeError, match="unavailable"):
            await emit(manager, trace_id)
        db.insert_prepared = original
        db.release.set()
        recovered = await manager.start_trace(
            "user",
            "session",
            "console",
            "source",
        )
        await emit(manager, recovered, input_tokens=19)
        await manager._writer.flush()
        await manager.end_trace(recovered)
        assert manager._writer.dropped_spans == 1
        assert db.trace_completed.is_set()
        assert not manager._writer._traces
    finally:
        fail.set()
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_lifecycle_capacity_rejects_without_leaking_and_recovers():
    manager, db, trace_id = await new_manager(max_queue_spans=1)
    db.release.set()
    create = manager.store.create_trace
    manager.store.create_trace = AsyncMock(wraps=create)
    try:
        with pytest.raises(RuntimeError, match="capacity exhausted"):
            await manager.start_trace("u2", "s2", "console", "source")
        manager.store.create_trace.assert_not_awaited()
        assert manager._writer.trace_count == 1
        await manager.end_trace(trace_id)
        recovered = await manager.start_trace("u2", "s2", "console", "source")
        await manager.end_trace(recovered)
        assert not manager._writer._traces
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_external_context_release_does_not_lose_pending_confirmation():
    manager, db, trace_id = await new_manager(max_queue_spans=2, batch_size=1)
    writer = manager._writer
    writer.register_trace("external", external=True)
    from swe.tracing.manager import TraceContext

    ctx = TraceContext(
        "external",
        "user",
        "session",
        "console",
        "source",
        attached=True,
    )
    ctx.release_writes = writer.attach_producer("external")
    set_current_trace(ctx)
    await emit(manager, "external")
    await db.started.wait()
    barrier = asyncio.create_task(writer.flush("external"))
    await asyncio.sleep(0)
    set_current_trace(None)
    try:
        assert writer.is_registered("external")
        assert writer.trace_count == 2
        db.release.set()
        await barrier
        assert not writer.is_registered("external")
        await manager.end_trace(trace_id)
        assert not writer._traces
    finally:
        db.release.set()
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
async def test_retired_batch_failure_cannot_invalidate_another_lifecycle(
    monkeypatch,
):
    monkeypatch.setattr("swe.tracing.writer._MAX_WRITE_ATTEMPTS", 1)
    manager, db, trace_id = await new_manager(batch_size=1)
    original = db.insert_prepared
    release = asyncio.Event()

    async def failing(*_args, **_kwargs):
        db.started.set()
        await release.wait()
        raise OSError("old batch failed")

    db.insert_prepared = failing
    await emit(manager, trace_id)
    await db.started.wait()
    manager._writer.mark_trace_unconfirmed(trace_id)
    # Simulate independent registration while an old entry still owns its state.
    manager._writer.register_trace(trace_id)
    new_state = manager._writer._traces[trace_id]
    release.set()
    try:
        async with manager._writer._changed:
            await asyncio.wait_for(
                manager._writer._changed.wait_for(
                    lambda: not manager._writer._entries,
                ),
                1,
            )
        assert manager._writer._traces[trace_id] is new_state
        assert not new_state.failed
        db.insert_prepared = original
        db.release.set()
        # This synthetic lifecycle is not a license to complete old aggregates.
        manager._writer.mark_trace_unconfirmed(trace_id)
        with pytest.raises(TimeoutError):
            await manager.end_trace(trace_id)
    finally:
        release.set()
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("pending_finalization", [False, True])
async def test_attachment_cannot_reset_failed_owner_confirmation(
    monkeypatch,
    pending_finalization,
):
    monkeypatch.setattr("swe.tracing.writer._MAX_WRITE_ATTEMPTS", 1)
    manager, db, trace_id = await new_manager(batch_size=1)
    db.release.set()
    owner_context = get_current_trace()
    update = manager.store.update_trace
    manager.store.update_trace = AsyncMock(
        side_effect=OSError("final update unavailable"),
    )
    try:
        if pending_finalization:
            with pytest.raises(OSError):
                await manager.end_trace(trace_id)
            assert trace_id in manager._pending_finalizations
        manager.store.update_trace = AsyncMock(wraps=update)
        db.insert_prepared = AsyncMock(side_effect=OSError("span lost"))
        await emit(manager, trace_id)
        async with manager._writer._changed:
            await asyncio.wait_for(
                manager._writer._changed.wait_for(
                    lambda: not manager._writer._entries,
                ),
                1,
            )
        assert not manager._writer.is_registered(trace_id)
        assert manager._writer.has_failed(trace_id)

        async def attach():
            await manager.start_trace(
                "user",
                "session",
                "console",
                "source",
                trace_id=trace_id,
                attach_existing=True,
            )

        # Run as a separate request, preserving the owner's context.
        if pending_finalization:
            manager.store.get_trace = AsyncMock(
                return_value=manager._pending_finalizations[trace_id][0],
            )
        with pytest.raises(RuntimeError, match="unconfirmed"):
            await asyncio.create_task(attach())
        assert not manager._writer.is_registered(trace_id)
        if not pending_finalization:
            assert get_current_trace() is owner_context
        with pytest.raises(TimeoutError, match="unconfirmed"):
            await manager.end_trace(trace_id)
        manager.store.update_trace.assert_not_awaited()
        assert not db.trace_completed.is_set()
        assert not manager._active_traces
        assert not manager._pending_finalizations
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("pending_finalization", [False, True])
async def test_attachment_reuses_healthy_owner_confirmation(
    pending_finalization,
):
    manager, db, trace_id = await new_manager(max_queue_spans=1)
    db.release.set()
    update = manager.store.update_trace
    try:
        if pending_finalization:
            manager.store.update_trace = AsyncMock(
                side_effect=OSError("unavailable"),
            )
            with pytest.raises(OSError):
                await manager.end_trace(trace_id)
            manager.store.get_trace = AsyncMock(
                return_value=manager._pending_finalizations[trace_id][0],
            )
            manager.store.update_trace = update
        state = manager._writer._traces[trace_id]

        async def attach():
            await manager.start_trace(
                "user",
                "session",
                "console",
                "source",
                trace_id=trace_id,
                attach_existing=True,
            )
            assert manager._writer._traces[trace_id] is state
            set_current_trace(None)

        await asyncio.create_task(attach())
        assert manager._writer._traces[trace_id] is state
        assert not state.external
        assert state.producers == 0
        await manager.end_trace(trace_id)
        assert db.trace_completed.is_set()
        assert not manager._writer._traces
    finally:
        await manager.close()
        set_current_trace(None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "child_action",
    ["clear", "attach", "cancel", "new_trace"],
)
async def test_child_context_switch_preserves_parent_attachment(child_action):
    manager, db, trace_id = await new_manager(batch_size=1)
    db.release.set()
    external = manager._active_traces.pop(trace_id)
    manager._writer.retire_trace(trace_id)
    set_current_trace(None)
    manager.store.get_trace = AsyncMock(return_value=external)

    async def attach():
        await manager.start_trace(
            "user",
            "session",
            "console",
            "source",
            trace_id=trace_id,
            attach_existing=True,
        )

    await attach()
    parent_ctx = get_current_trace()
    state = manager._writer._traces[trace_id]
    child_attached = asyncio.Event()

    async def child():
        assert get_current_trace() is parent_ctx
        try:
            if child_action == "clear":
                set_current_trace(None)
            elif child_action == "new_trace":
                own_id = await manager.start_trace(
                    "u2",
                    "s2",
                    "console",
                    "source",
                )
                await manager.end_trace(own_id)
            else:
                await attach()
                assert state.producers == 2
                child_attached.set()
                if child_action == "cancel":
                    await asyncio.Event().wait()
                await emit(manager, trace_id)
                await manager._writer.flush(trace_id)
        finally:
            set_current_trace(None)

    task = asyncio.create_task(child())
    try:
        if child_action == "cancel":
            await asyncio.wait_for(child_attached.wait(), 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
        assert get_current_trace() is parent_ctx
        assert manager._writer._traces.get(trace_id) is state
        assert state.producers == 1
        await emit(manager, trace_id)
        await manager._writer.flush(trace_id)
        # Replacing an attachment in its owning task must release the old one.
        await attach()
        assert state.producers == 1
        set_current_trace(None)
        assert not manager._writer.is_registered(trace_id)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        set_current_trace(None)
        await manager.close()
