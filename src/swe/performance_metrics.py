# -*- coding: utf-8 -*-
"""Bounded process-local performance measurements without tenant labels."""

from collections import deque
from collections.abc import Callable
import math
import threading
import time
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")
_SAMPLE_LIMIT = 2048
_WORKERS = ("output", "runtime_state", "provider", "backup", "stream")
_COUNTERS = ("checkpoint_read_bytes", "checkpoint_read_calls", "s3_list_pages")
_STREAM_STAGES = (
    "admission",
    "batch_wait",
    "accepted_to_committed",
    "write_queue",
    "write_execution",
    "read_queue",
    "read_execution",
    "read_total",
)


def _summary(values: list[float], prefix: str) -> dict:
    ordered = sorted(values)
    result = {
        f"{prefix}_avg_ms": sum(values) / len(values) if values else None,
    }
    for percentile in (95, 99):
        result[f"{prefix}_p{percentile}_ms"] = (
            ordered[math.ceil(len(ordered) * percentile / 100) - 1]
            if ordered
            else None
        )
    result[f"{prefix}_max_ms"] = max(values) if values else None
    return result


class PerformanceMetrics:
    """Keep rolling task timings and cumulative I/O counters under a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: dict[str, deque[tuple[float, float]]] = {
            name: deque(maxlen=_SAMPLE_LIMIT) for name in _WORKERS
        }
        self._completed = dict.fromkeys(_WORKERS, 0)
        self._counters = dict.fromkeys(_COUNTERS, 0)
        self._stream_samples: dict[str, deque[float]] = {
            name: deque(maxlen=_SAMPLE_LIMIT) for name in _STREAM_STAGES
        }
        self._stream_observed = dict.fromkeys(_STREAM_STAGES, 0)

    def record_stream_timing(self, stage: str, seconds: float) -> None:
        if stage not in self._stream_samples:
            raise ValueError("Unknown stream performance stage")
        with self._lock:
            self._stream_samples[stage].append(max(0.0, seconds) * 1000)
            self._stream_observed[stage] += 1

    def record_worker_timing(
        self,
        worker: str,
        queue_seconds: float,
        execution_seconds: float,
    ) -> None:
        if worker not in self._samples:
            raise ValueError("Unknown performance worker")
        with self._lock:
            self._samples[worker].append(
                (
                    max(0.0, queue_seconds) * 1000,
                    max(0.0, execution_seconds) * 1000,
                ),
            )
            self._completed[worker] += 1

    def increment(self, name: str, value: int = 1) -> None:
        if name not in self._counters:
            raise ValueError("Unknown performance counter")
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict:
        with self._lock:
            samples = {
                name: list(rows) for name, rows in self._samples.items()
            }
            completed = self._completed.copy()
            counters = self._counters.copy()
            stream_samples = {
                name: list(rows) for name, rows in self._stream_samples.items()
            }
            stream_observed = self._stream_observed.copy()
        workers = {}
        for name, rows in samples.items():
            workers[name] = {
                "completed_count": completed[name],
                "sample_count": len(rows),
                **_summary([row[0] for row in rows], "queue"),
                **_summary([row[1] for row in rows], "execution"),
            }
        stream_stages = {
            name: {
                "observed_count": stream_observed[name],
                "sample_count": len(rows),
                **_summary(rows, "duration"),
            }
            for name, rows in stream_samples.items()
        }
        return {
            "workers": workers,
            "counters": counters,
            "stream_stages": stream_stages,
        }


METRICS = PerformanceMetrics()


def record_stream_timing(stage: str, seconds: float) -> None:
    """Record one bounded SSE stage observation without payload references."""
    METRICS.record_stream_timing(stage, seconds)


def increment(name: str, value: int = 1) -> None:
    """Record actual checkpoint payload reads or attempted S3 page calls."""
    METRICS.increment(name, value)


def timed_work(
    worker: str,
    queued_at: float,
    function: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Measure wait until real thread start and execution until real finish."""
    started = time.monotonic()
    try:
        return function(*args, **kwargs)
    finally:
        METRICS.record_worker_timing(
            worker,
            started - queued_at,
            time.monotonic() - started,
        )
