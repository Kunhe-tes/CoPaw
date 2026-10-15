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
        workers = {}
        for name, rows in samples.items():
            workers[name] = {
                "completed_count": completed[name],
                "sample_count": len(rows),
                **_summary([row[0] for row in rows], "queue"),
                **_summary([row[1] for row in rows], "execution"),
            }
        return {"workers": workers, "counters": counters}


METRICS = PerformanceMetrics()


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
