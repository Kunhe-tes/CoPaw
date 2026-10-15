# -*- coding: utf-8 -*-
"""Bounded shared SSE replay storage and cursor subscriptions."""

import asyncio
import threading

import pytest

from swe.app.runner.sse_replay import (
    ReplayBudget,
    ReplayLog,
    ReplayStream,
    ReplayUnavailable,
)


@pytest.mark.asyncio
async def test_log_replays_in_order_in_byte_bounded_batches():
    budget = ReplayBudget(max_bytes=4096)
    log = ReplayLog(budget=budget, max_bytes=4096)
    try:
        for index in range(20):
            assert await log.append(f"data: {index}\n\n") == index + 1
        batch = await log.read(1, max_bytes=40)
        assert [seq for seq, _ in batch] == list(range(1, len(batch) + 1))
        assert sum(len(text.encode()) for _, text in batch) <= 40
        assert await log.read(20) == [(20, "data: 19\n\n")]
        assert budget.used_bytes > 0
    finally:
        await log.aclose()
    assert budget.used_bytes == 0


@pytest.mark.asyncio
async def test_log_quota_failure_does_not_publish_or_leak_budget():
    budget = ReplayBudget(max_bytes=80)
    first = ReplayLog(budget=budget, max_bytes=80)
    second = ReplayLog(budget=budget, max_bytes=80)
    try:
        await first.append("a" * 40)
        used = budget.used_bytes
        with pytest.raises(ReplayUnavailable):
            await second.append("b" * 40)
        assert second.count == 0
        assert budget.used_bytes == used
        assert await first.read(1) == [(1, "a" * 40)]
    finally:
        await first.aclose()
        await second.aclose()
    assert budget.used_bytes == 0


@pytest.mark.asyncio
async def test_slow_subscription_does_not_retain_events_or_block_fast_one():
    stream = ReplayStream()
    slow = stream.subscribe()
    fast = stream.subscribe()
    try:
        for index in range(150):
            event = f"data: {index}\n\n"
            await stream.append(event)
            assert await fast.get() == event
        assert slow.buffered_bytes == 0
        assert slow.last_sequence == 0
        stream.finish()
        assert [await slow.get() for _ in range(150)] == [
            f"data: {i}\n\n" for i in range(150)
        ]
        assert await slow.get() is None
        assert await fast.get() is None
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_subscription_cursor_and_control_do_not_need_queue_capacity():
    stream = ReplayStream()
    try:
        for index in range(3):
            await stream.append(f"data: {index}\n\n")
        subscriber = stream.subscribe()
        subscriber.seek(2)
        assert await subscriber.get() == "data: 2\n\n"
        with pytest.raises(ReplayUnavailable):
            subscriber.seek(4)
        subscriber.interrupt("slow_consumer", retryable=True)
        assert "stream.recover" in await subscriber.get()
        assert await subscriber.get() is None
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_close_wakes_waiting_subscriber():
    stream = ReplayStream()
    subscriber = stream.subscribe()
    waiting = asyncio.create_task(subscriber.get())
    await asyncio.sleep(0)
    await stream.aclose()
    assert await asyncio.wait_for(waiting, 1) is None


@pytest.mark.asyncio
async def test_resume_rejects_other_turn_and_reads_only_after_cursor():
    stream = ReplayStream()
    subscriber = stream.subscribe()
    try:
        await stream.append("data: first\n\n")
        await stream.append("data: second\n\n")
        subscriber.resume("turn-a", "turn-a:1")
        assert await subscriber.get() == "data: second\n\n"
        with pytest.raises(ReplayUnavailable):
            subscriber.resume("turn-a", "turn-b:1")
        with pytest.raises(ReplayUnavailable):
            subscriber.resume("turn-a", "turn-a:3")
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_only_negotiated_slow_subscriber_is_interrupted(monkeypatch):
    from swe.app.runner import sse_replay

    stream = ReplayStream()
    slow = stream.subscribe()
    legacy = stream.subscribe()
    slow.resumable = True
    monkeypatch.setattr(sse_replay, "SLOW_SUBSCRIBER_SECONDS", 0)
    monkeypatch.setattr(sse_replay, "SLOW_SUBSCRIBER_BYTES", 1)
    try:
        await stream.append("data: enough lag\n\n")
        assert "stream.recover" in await slow.get()
        assert await legacy.get() == "data: enough lag\n\n"
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_stream_worker_and_budget_are_observable(monkeypatch):
    from swe import performance_metrics
    from swe.app.runner.sse_replay import run_stream_io

    metrics = performance_metrics.PerformanceMetrics()
    monkeypatch.setattr(performance_metrics, "METRICS", metrics)
    assert await run_stream_io(lambda: "ok") == "ok"
    assert metrics.snapshot()["workers"]["stream"]["completed_count"] == 1
    budget = ReplayBudget(max_bytes=100)
    assert budget.snapshot()["reserved_bytes"] == 0
    budget.reserve(50)
    assert budget.snapshot()["reserved_bytes"] == 50
    with pytest.raises(ReplayUnavailable):
        budget.reserve(60)
    assert budget.snapshot()["quota_rejections"] == 1
    budget.release(50)


@pytest.mark.asyncio
async def test_process_subscriber_memory_is_reserved_until_delivery_advances():
    budget = ReplayBudget()
    stream = ReplayStream(ReplayLog(budget=budget))
    subscriber = stream.subscribe()
    try:
        await stream.append("data: payload\n\n")
        assert await subscriber.get() == "data: payload\n\n"
        assert budget.snapshot()["subscriber_memory_bytes"] > 0
        stream.finish()
        assert await subscriber.get() is None
        assert budget.snapshot()["subscriber_memory_bytes"] == 0
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_cancelled_publish_waits_for_worker_then_commits(monkeypatch):
    stream = ReplayStream()
    subscriber = stream.subscribe()
    started, release = threading.Event(), threading.Event()
    original = stream.log._append

    def delayed(text):
        started.set()
        assert release.wait(5)
        return original(text)

    monkeypatch.setattr(stream.log, "_append", delayed)
    task = asyncio.create_task(stream.append("data: retained\n\n"))
    try:
        async with asyncio.timeout(5):
            while not started.is_set():
                await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    try:
        assert stream.committed == 1
        assert await subscriber.get() == "data: retained\n\n"
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_short_write_rolls_back_quota_and_does_not_publish(monkeypatch):
    import tempfile

    budget = ReplayBudget()
    log = ReplayLog(budget=budget)
    file = tempfile.TemporaryFile(mode="w+b", buffering=0)

    class ShortFile:
        def write(self, data):
            return file.write(data[:-1])

        def __getattr__(self, name):
            return getattr(file, name)

    log.file = ShortFile()
    try:
        with pytest.raises(OSError, match="Incomplete"):
            await log.append("data: incomplete\n\n")
        assert log.count == 0
        assert file.seek(0, 2) == 0
        assert budget.used_bytes == 0
    finally:
        await log.aclose()


@pytest.mark.asyncio
async def test_expired_replay_cannot_look_like_a_successful_end():
    stream = ReplayStream()
    subscriber = stream.subscribe()
    await stream.append("data: unread\n\n")
    stream.finish()
    await stream.aclose()
    control = await subscriber.get()
    assert control is not None and "stream.unavailable" in control
    assert await subscriber.get() is None
