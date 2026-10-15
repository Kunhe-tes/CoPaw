# -*- coding: utf-8 -*-
"""Bounded performance accounting and real execution boundary tests."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest


def test_stream_stage_samples_are_bounded_and_have_fixed_labels():
    from swe.performance_metrics import PerformanceMetrics

    metrics = PerformanceMetrics()
    for value in range(1, 2101):
        metrics.record_stream_timing("admission", value / 1000)
    stages = metrics.snapshot()["stream_stages"]
    assert set(stages) == {
        "admission",
        "batch_wait",
        "accepted_to_committed",
        "write_queue",
        "write_execution",
        "read_queue",
        "read_execution",
        "read_total",
    }
    result = stages["admission"]
    assert result["observed_count"] == 2100
    assert result["sample_count"] == 2048
    assert result["duration_p95_ms"] == 1998
    assert result["duration_p99_ms"] == 2080
    assert stages["read_total"]["duration_p99_ms"] is None
    with pytest.raises(ValueError):
        metrics.record_stream_timing("tenant-secret", 0)


def test_stream_stage_timings_are_thread_safe():
    from swe.performance_metrics import PerformanceMetrics

    metrics = PerformanceMetrics()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda _: metrics.record_stream_timing(
                    "write_execution",
                    0.002,
                ),
                range(500),
            ),
        )
    result = metrics.snapshot()["stream_stages"]["write_execution"]
    assert result["observed_count"] == 500
    assert result["duration_p99_ms"] == 2


def test_metrics_bound_samples_and_keep_cumulative_counts():
    from swe.performance_metrics import PerformanceMetrics

    metrics = PerformanceMetrics()
    for value in range(1, 2101):
        metrics.record_worker_timing("output", value / 1000, value / 500)
    metrics.increment("checkpoint_read_bytes", 12)
    metrics.increment("checkpoint_read_calls")
    snapshot = metrics.snapshot()
    output = snapshot["workers"]["output"]
    assert output["completed_count"] == 2100
    assert output["sample_count"] == 2048
    assert output["queue_p95_ms"] == 1998
    assert output["queue_p99_ms"] == 2080
    assert output["execution_p99_ms"] == 4160
    assert snapshot["counters"]["checkpoint_read_bytes"] == 12
    assert snapshot["counters"]["checkpoint_read_calls"] == 1


def test_metrics_are_thread_safe_and_have_fixed_labels():
    from swe.performance_metrics import PerformanceMetrics

    metrics = PerformanceMetrics()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(lambda _: metrics.increment("s3_list_pages"), range(500)),
        )
    assert metrics.snapshot()["counters"]["s3_list_pages"] == 500
    with pytest.raises(ValueError):
        metrics.increment("tenant-secret")
    with pytest.raises(ValueError):
        metrics.record_worker_timing("tenant-secret", 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "worker",
    ["output", "runtime_state", "backup", "provider"],
)
async def test_actual_workers_record_execution_and_exception(
    monkeypatch,
    worker,
):
    from swe import performance_metrics

    metrics = performance_metrics.PerformanceMetrics()
    monkeypatch.setattr(performance_metrics, "METRICS", metrics)

    def work():
        time.sleep(0.015)
        raise ValueError("expected failure")

    with pytest.raises(ValueError, match="expected failure"):
        if worker == "output":
            from swe.output_workers import run_output_work

            await run_output_work(work)
        elif worker == "runtime_state":
            from swe.runtime_workers import run_runtime_state_work

            await run_runtime_state_work(work)
        elif worker == "backup":
            from swe.app.backup.io_worker import run_backup_io

            await run_backup_io(work)
        else:
            from swe.providers.provider_runtime_cache import (
                ProviderRuntimeCache,
            )

            cache = ProviderRuntimeCache()
            try:
                await asyncio.wrap_future(cache.submit(work))
            finally:
                cache.init_executor.shutdown()
    result = metrics.snapshot()["workers"][worker]
    assert result["completed_count"] == 1
    assert result["queue_p99_ms"] >= 0
    assert result["execution_p99_ms"] >= 10


@pytest.mark.asyncio
async def test_output_queue_wait_and_cancelled_work_are_measured(monkeypatch):
    from swe import output_workers, performance_metrics

    metrics = performance_metrics.PerformanceMetrics()
    monkeypatch.setattr(performance_metrics, "METRICS", metrics)
    monkeypatch.setattr(
        output_workers,
        "_SLOTS",
        threading.BoundedSemaphore(1),
    )
    started = threading.Event()
    release = threading.Event()

    def work():
        started.set()
        assert release.wait(5)

    first = asyncio.create_task(output_workers.run_output_work(work))
    while not started.is_set():
        await asyncio.sleep(0.001)
    second = asyncio.create_task(output_workers.run_output_work(lambda: None))
    try:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await asyncio.sleep(0.02)
        assert metrics.snapshot()["workers"]["output"]["completed_count"] == 0
    finally:
        release.set()
    await asyncio.wait_for(second, 5)
    result = metrics.snapshot()["workers"]["output"]
    assert result["completed_count"] == 2
    assert result["queue_p99_ms"] >= 10


def test_provider_startup_is_counted_once_for_shared_future(monkeypatch):
    from swe import performance_metrics
    from swe.providers.provider_runtime_cache import ProviderRuntimeCache

    metrics = performance_metrics.PerformanceMetrics()
    monkeypatch.setattr(performance_metrics, "METRICS", metrics)
    cache = ProviderRuntimeCache()
    try:
        expected = object()
        future = cache.get_or_start_instance("tenant-a", lambda _: expected)
        assert future.result(timeout=5) is expected
        assert (
            cache.get_or_start_instance("tenant-a", lambda _: None).result()
            is expected
        )
        assert (
            metrics.snapshot()["workers"]["provider"]["completed_count"] == 1
        )
    finally:
        cache.init_executor.shutdown()
