# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import threading

import pytest

from swe.app.runner.task_tracker import TaskTracker, _RunState
from swe.app.runner.tool_output_frames import (
    emit_tool_output_text,
    tool_output_invocation,
)


@pytest.mark.asyncio
async def test_stop_claim_requires_matching_turn_id_and_does_not_cancel_immediately():
    tracker = TaskTracker()
    release_stream = asyncio.Event()

    async def _stream_fn(_payload):
        yield 'data: {"before": true}\n\n'
        await release_stream.wait()

    queue, is_new = await tracker.attach_or_start(
        "chat-turn",
        {},
        _stream_fn,
        msgid="turn-1",
    )
    assert is_new is True
    assert await queue.get()

    wrong = await tracker.request_stop("chat-turn", msgid="turn-2")
    assert wrong.accepted is False
    assert await tracker.get_status("chat-turn") == "running"

    accepted = await tracker.request_stop("chat-turn", msgid="turn-1")
    assert accepted.accepted is True
    assert accepted.chat_id == "chat-turn"
    assert accepted.msgid == "turn-1"
    assert await tracker.get_status("chat-turn") == "stopping"

    release_stream.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_console_legacy_stop_is_cooperative_and_exposes_active_turn_id():
    tracker = TaskTracker()
    release_stream = asyncio.Event()

    async def _stream_fn(_payload):
        yield 'data: {"before": true}\n\n'
        await release_stream.wait()

    queue, is_new = await tracker.attach_or_start(
        "chat-console-legacy",
        {},
        _stream_fn,
        msgid="turn-server",
    )
    assert is_new is True
    assert await queue.get()

    identity = await tracker.get_run_identity("chat-console-legacy")
    assert identity == ("chat-console-legacy", "turn-server")

    claim = await tracker.claim_stop(
        "chat-console-legacy",
        cooperative=True,
    )
    assert claim.accepted is True
    assert claim.msgid == "turn-server"
    assert await tracker.get_status("chat-console-legacy") == "stopping"

    release_stream.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_stop_claim_freezes_output_for_existing_and_reconnecting_subscribers():
    tracker = TaskTracker()
    release_stream = asyncio.Event()
    queue, _ = await tracker.attach_or_start(
        "chat-freeze",
        {},
        lambda _payload: _stream(release_stream),
        msgid="turn-1",
    )
    assert await queue.get()

    accepted = await tracker.request_stop("chat-freeze", msgid="turn-1")
    assert accepted.accepted is True

    reconnect = await tracker.attach("chat-freeze")
    assert reconnect is not None
    assert await reconnect.get()
    release_stream.set()
    assert await asyncio.wait_for(queue.get(), timeout=1) is None
    assert await asyncio.wait_for(reconnect.get(), timeout=1) is None
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


async def _stream(release_stream):
    yield 'data: {"before": true}\n\n'
    await release_stream.wait()
    yield 'data: {"after": true}\n\n'


@pytest.mark.asyncio
async def test_request_stop_marks_status_stopping_while_producer_is_cleaning_up():
    tracker = TaskTracker()
    stream_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def _stream_fn(_payload):
        stream_started.set()
        yield 'data: {"started": true}\n\n'
        try:
            while True:
                await asyncio.sleep(1)
                yield 'data: {"tick": true}\n\n'
        finally:
            cleanup_started.set()
            await release_cleanup.wait()

    _queue, is_new = await tracker.attach_or_start(
        "chat-1",
        {},
        _stream_fn,
    )
    assert is_new is True
    await asyncio.wait_for(stream_started.wait(), timeout=1)
    assert await tracker.get_status("chat-1") == "running"

    assert await tracker.request_stop("chat-1") is True
    await asyncio.wait_for(cleanup_started.wait(), timeout=1)

    assert await tracker.get_status("chat-1") == "stopping"

    release_cleanup.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)
    assert await tracker.get_status("chat-1") == "idle"


@pytest.mark.asyncio
async def test_mark_stopping_marks_status_without_cancelling_producer():
    tracker = TaskTracker()
    release_stream = asyncio.Event()

    async def _stream_fn(_payload):
        yield 'data: {"started": true}\n\n'
        await release_stream.wait()

    _queue, is_new = await tracker.attach_or_start(
        "chat-1",
        {},
        _stream_fn,
    )
    assert is_new is True
    await asyncio.sleep(0)
    assert await tracker.get_status("chat-1") == "running"

    await tracker.mark_stopping("chat-1")

    assert await tracker.get_status("chat-1") == "stopping"

    release_stream.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)
    assert await tracker.get_status("chat-1") == "idle"


@pytest.mark.asyncio
async def test_before_start_runs_before_producer_and_failed_hook_leaves_no_run():
    tracker = TaskTracker()
    order: list[str] = []

    async def _stream_fn(_payload):
        order.append("producer")
        yield 'data: {"done": true}\n\n'

    queue, is_new = await tracker.attach_or_start(
        "chat-before-start",
        {},
        _stream_fn,
        before_start=lambda: order.append("before_start"),
    )
    assert is_new is True
    assert await asyncio.wait_for(queue.get(), timeout=1)
    assert order == ["before_start", "producer"]

    def fail_before_start() -> None:
        raise RuntimeError("claim consume failed")

    with pytest.raises(RuntimeError, match="claim consume failed"):
        await tracker.attach_or_start(
            "chat-failed-hook",
            {},
            _stream_fn,
            before_start=fail_before_start,
        )
    assert await tracker.get_status("chat-failed-hook") == "idle"
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)
    assert await tracker.get_status("chat-before-start") == "idle"


@pytest.mark.asyncio
async def test_idle_callback_and_task_registration_share_one_lock():
    tracker = TaskTracker()
    durable_state = {"active": True}
    callback_started = threading.Event()
    release_callback = threading.Event()

    def recover():
        durable_state["active"] = False
        callback_started.set()
        assert release_callback.wait(timeout=2)
        return "recovered"

    recovery_task = asyncio.create_task(
        tracker.call_if_idle("chat-serialized", recover),
    )
    assert await asyncio.to_thread(callback_started.wait, 1)

    async def _stream_fn(_payload):
        yield 'data: {"started": true}\n\n'

    def validate_claim() -> None:
        if not durable_state["active"]:
            raise RuntimeError("claim is no longer active")

    start_task = asyncio.create_task(
        tracker.attach_or_start(
            "chat-serialized",
            {},
            _stream_fn,
            before_start=validate_claim,
        ),
    )
    await asyncio.sleep(0)
    assert start_task.done() is False

    release_callback.set()
    was_idle, result = await recovery_task
    assert was_idle is True
    assert result == "recovered"
    with pytest.raises(RuntimeError, match="claim is no longer active"):
        await start_task
    assert await tracker.get_status("chat-serialized") == "idle"


@pytest.mark.asyncio
async def test_active_task_prevents_idle_callback():
    tracker = TaskTracker()
    release_stream = asyncio.Event()
    callback_called = False

    async def _stream_fn(_payload):
        yield 'data: {"started": true}\n\n'
        await release_stream.wait()

    await tracker.attach_or_start(
        "chat-active",
        {},
        _stream_fn,
    )
    await asyncio.sleep(0)

    def callback():
        nonlocal callback_called
        callback_called = True

    was_idle, result = await tracker.call_if_idle(
        "chat-active",
        callback,
    )

    assert was_idle is False
    assert result is None
    assert callback_called is False

    release_stream.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_slow_idle_callback_does_not_block_another_run_key():
    tracker = TaskTracker()
    callback_started = threading.Event()
    release_callback = threading.Event()

    def slow_callback():
        callback_started.set()
        assert release_callback.wait(timeout=2)
        return "done"

    recovery_task = asyncio.create_task(
        tracker.call_if_idle("chat-slow", slow_callback),
    )
    assert await asyncio.to_thread(callback_started.wait, 1)

    async def _stream_fn(_payload):
        yield 'data: {"done": true}\n\n'

    queue, is_new = await asyncio.wait_for(
        tracker.attach_or_start("chat-other", {}, _stream_fn),
        timeout=0.5,
    )
    assert is_new is True
    assert await asyncio.wait_for(queue.get(), timeout=1)

    release_callback.set()
    assert await recovery_task == (True, "done")
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_slow_before_start_does_not_block_another_run_key():
    tracker = TaskTracker()
    callback_started = threading.Event()
    release_callback = threading.Event()

    def slow_before_start():
        callback_started.set()
        assert release_callback.wait(timeout=2)

    async def _stream_fn(_payload):
        yield 'data: {"done": true}\n\n'

    slow_start = asyncio.create_task(
        tracker.attach_or_start(
            "chat-slow-start",
            {},
            _stream_fn,
            before_start=slow_before_start,
        ),
    )
    assert await asyncio.to_thread(callback_started.wait, 1)

    queue, is_new = await asyncio.wait_for(
        tracker.attach_or_start("chat-other-start", {}, _stream_fn),
        timeout=0.5,
    )
    assert is_new is True
    assert await asyncio.wait_for(queue.get(), timeout=1)

    release_callback.set()
    slow_queue, slow_is_new = await slow_start
    assert slow_is_new is True
    assert await asyncio.wait_for(slow_queue.get(), timeout=1)
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_cancelled_before_start_finishes_atomic_registration():
    tracker = TaskTracker()
    callback_started = threading.Event()
    release_callback = threading.Event()
    release_stream = asyncio.Event()
    claim_consumed = False

    def consume_claim():
        nonlocal claim_consumed
        claim_consumed = True
        callback_started.set()
        assert release_callback.wait(timeout=2)

    async def _stream_fn(_payload):
        yield 'data: {"started": true}\n\n'
        await release_stream.wait()

    start_task = asyncio.create_task(
        tracker.attach_or_start(
            "chat-cancelled-start",
            {},
            _stream_fn,
            before_start=consume_claim,
        ),
    )
    assert await asyncio.to_thread(callback_started.wait, 1)
    start_task.cancel()
    release_callback.set()

    queue, is_new = await start_task

    assert claim_consumed is True
    assert is_new is True
    assert await asyncio.wait_for(queue.get(), timeout=1)
    assert await tracker.get_status("chat-cancelled-start") == "running"

    release_stream.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_old_run_cleanup_does_not_remove_new_run_state():
    tracker = TaskTracker()
    first_cleanup_started = asyncio.Event()
    release_first_cleanup = asyncio.Event()

    async def _first_stream(_payload):
        yield 'data: {"run": 1}\n\n'
        try:
            while True:
                await asyncio.sleep(1)
        finally:
            first_cleanup_started.set()
            await release_first_cleanup.wait()

    _queue, is_new = await tracker.attach_or_start(
        "chat-1",
        {},
        _first_stream,
    )
    assert is_new is True
    await asyncio.sleep(0)
    assert await tracker.request_stop("chat-1") is True
    await asyncio.wait_for(first_cleanup_started.wait(), timeout=1)
    assert await tracker.get_status("chat-1") == "stopping"

    second_task = asyncio.Future()
    async with tracker.lock:
        tracker._runs["chat-1"] = _RunState(task=second_task)

    assert await tracker.get_status("chat-1") == "running"

    release_first_cleanup.set()
    await asyncio.sleep(0)
    assert await tracker.get_status("chat-1") == "running"

    second_task.set_result(None)
    async with tracker.lock:
        tracker._runs.pop("chat-1", None)
    assert await tracker.get_status("chat-1") == "idle"


@pytest.mark.asyncio
async def test_tool_output_frames_are_buffered_for_active_replay():
    tracker = TaskTracker()
    release_stream = asyncio.Event()

    async def _stream_fn(_payload):
        with tool_output_invocation(
            tool_call_id="call-1",
            tool_name="execute_shell_command",
        ):
            await emit_tool_output_text("stdout", "live output\n")
        yield 'data: {"normal": true}\n\n'
        await release_stream.wait()

    queue, is_new = await tracker.attach_or_start("chat-1", {}, _stream_fn)
    assert is_new is True

    live_sse = await asyncio.wait_for(queue.get(), timeout=1)
    assert live_sse.startswith("data: ")
    live_payload = json.loads(live_sse.removeprefix("data: ").strip())
    assert live_payload == {
        "object": "tool_output_frame",
        "tool_call_id": "call-1",
        "tool_name": "execute_shell_command",
        "sequence": 1,
        "source": "stdout",
        "text": "live output\n",
        "truncated": False,
        "budget_bytes": 50 * 1024,
    }

    replay_queue = await tracker.attach("chat-1")
    assert replay_queue is not None
    replay_sse = await asyncio.wait_for(replay_queue.get(), timeout=1)
    replay_payload = json.loads(replay_sse.removeprefix("data: ").strip())
    assert replay_payload["object"] == "tool_output_frame"
    assert replay_payload["text"] == "live output\n"

    release_stream.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)
