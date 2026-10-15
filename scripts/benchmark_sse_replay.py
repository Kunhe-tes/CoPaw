# -*- coding: utf-8 -*-
"""Compare legacy in-memory transport with cursor replay; no HTTP/model/DB."""

import argparse
import asyncio
import json
import math
import time

import psutil

from swe.app.runner.sse_replay import ReplayStream, _BUDGET
from swe.performance_metrics import METRICS


async def benchmark(options):
    process = psutil.Process()
    rss_start = process.memory_info().rss
    peak = rss_start
    lag = []
    stop = asyncio.Event()

    async def sample():
        nonlocal peak
        while not stop.is_set():
            before = time.monotonic()
            await asyncio.sleep(0.005)
            lag.append(max(0, time.monotonic() - before - 0.005) * 1000)
            peak = max(peak, process.memory_info().rss)

    streams = []
    retained = []
    slow = []
    sampler = asyncio.create_task(sample())

    async def run(tenant):
        if options.legacy:
            history, queue = [], asyncio.Queue()
            retained.append(history)
            slow.append(queue)
        else:
            stream = ReplayStream()
            streams.append(stream)
            slow.append(stream.subscribe())
            fast = stream.subscribe()
        for index in range(options.events):
            event = (
                "data: "
                + json.dumps(
                    {"tenant": tenant, "index": index, "text": "x" * 1000},
                )
                + "\n\n"
            )
            if options.legacy:
                history.append(event)
                queue.put_nowait(event)
                if index % 64 == 0:
                    await asyncio.sleep(0)
            else:
                await stream.append(event)
                assert await fast.get() == event

    started = time.monotonic()
    try:
        await asyncio.gather(
            *(run(tenant) for tenant in range(options.tenants)),
        )
        elapsed = time.monotonic() - started
        await asyncio.sleep(0.01)
        ordered = sorted(lag)
        result = {
            "mode": (
                "legacy-kernel-simulation"
                if options.legacy
                else "cursor-replay"
            ),
            "tenant_count": options.tenants,
            "events_per_tenant": options.events,
            "elapsed_seconds": elapsed,
            "rss_start_bytes": rss_start,
            "rss_finish_bytes": process.memory_info().rss,
            "rss_sampled_peak_bytes": peak,
            "event_loop_lag_p95_ms": ordered[
                max(0, math.ceil(len(ordered) * 0.95) - 1)
            ],
            "event_loop_lag_p99_ms": ordered[
                max(0, math.ceil(len(ordered) * 0.99) - 1)
            ],
            "lag_sample_count": len(lag),
            "slow_subscriber_buffered_payload_bytes": (
                None
                if options.legacy
                else sum(sub.buffered_bytes for sub in slow)
            ),
            "legacy_slow_queue_entries": (
                sum(queue.qsize() for queue in slow) if options.legacy else 0
            ),
            "replay_budget": _BUDGET.snapshot(),
            "stream_worker": METRICS.snapshot()["workers"]["stream"],
            "scope": "local kernels, one fast and one stalled subscriber per simulated tenant; no HTTP/model/DB",
        }
    finally:
        stop.set()
        await sampler
        for stream in streams:
            await stream.aclose()
    result["replay_budget_after_close"] = _BUDGET.snapshot()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--tenants", type=int, default=4)
    parser.add_argument("--events", type=int, default=5000)
    options = parser.parse_args()
    if options.tenants < 1 or options.events < 1:
        parser.error("tenants and events must be positive")
    asyncio.run(benchmark(options))
