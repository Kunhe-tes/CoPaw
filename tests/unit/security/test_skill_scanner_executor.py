# -*- coding: utf-8 -*-
"""Tests for skill scanner executor lifecycle."""

from __future__ import annotations

import asyncio
from pathlib import Path
import threading
import time
import pytest

from swe.security import skill_scanner
from swe.security.skill_scanner.models import ScanResult


class _FakeFuture:
    def __init__(self, result):
        self._result = result
        self._cancelled = False

    def result(self, timeout=None):  # pylint: disable=unused-argument
        return self._result

    def cancel(self):
        self._cancelled = True
        return True

    def cancelled(self):
        return self._cancelled

    def add_done_callback(self, callback):
        if self._cancelled:
            callback(self)


def test_scan_skill_directory_reuses_scan_executor(
    monkeypatch,
    tmp_path: Path,
) -> None:
    created_executors = []
    submitted_paths = []

    class _FakeExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers
            created_executors.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def submit(self, fn, scanner, resolved, **kwargs):
            submitted_paths.append(resolved)
            return _FakeFuture(fn(scanner, resolved, **kwargs))

    class _FakeScanner:
        def scan_skill(self, resolved, *, skill_name=None):
            return ScanResult(
                skill_name=skill_name or Path(resolved).name,
                skill_directory=str(resolved),
            )

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("SWE_SKILL_SCAN_MODE", "warn")
    monkeypatch.setenv("SWE_SKILL_SCAN_EXECUTOR_WORKERS", "2")
    monkeypatch.setattr(skill_scanner, "_scanner_instance", _FakeScanner())
    monkeypatch.setattr(skill_scanner, "_scan_executor", None)
    monkeypatch.setattr(skill_scanner, "_scan_executor_workers", None)
    monkeypatch.setattr(skill_scanner, "_scan_executor_slots", None)
    monkeypatch.setattr(skill_scanner, "_scan_cache", {})
    monkeypatch.setattr(
        skill_scanner.futures,
        "ThreadPoolExecutor",
        _FakeExecutor,
    )

    skill_scanner.scan_skill_directory(first)
    skill_scanner.scan_skill_directory(first)
    skill_scanner.scan_skill_directory(second)

    assert [executor.max_workers for executor in created_executors] == [2]
    assert submitted_paths == [first.resolve(), second.resolve()]


@pytest.mark.asyncio
async def test_async_scan_cancellation_returns_without_waiting_for_worker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "cancelled"
    skill_dir.mkdir()
    started = threading.Event()
    finished = threading.Event()

    def slow_scan(*_args, **_kwargs):
        started.set()
        time.sleep(0.08)
        finished.set()

    monkeypatch.setattr(skill_scanner, "scan_skill_directory", slow_scan)
    task = asyncio.create_task(
        skill_scanner.scan_skill_directory_async(skill_dir),
    )
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(finished.wait, 1)


def test_scan_skill_directory_times_out_before_queueing_when_slots_busy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    submitted_paths = []

    class _FakeExecutor:
        def submit(self, fn, resolved, **kwargs):
            del fn, kwargs
            submitted_paths.append(resolved)
            raise AssertionError("scan should not be submitted")

    skill_dir = tmp_path / "blocked"
    skill_dir.mkdir()
    slot = threading.BoundedSemaphore(1)  # pylint: disable=consider-using-with
    assert slot.acquire(blocking=False)  # pylint: disable=consider-using-with

    monkeypatch.setenv("SWE_SKILL_SCAN_MODE", "warn")
    monkeypatch.setenv("SWE_SKILL_SCAN_EXECUTOR_WORKERS", "1")
    monkeypatch.setattr(skill_scanner, "_scan_executor", _FakeExecutor())
    monkeypatch.setattr(skill_scanner, "_scan_executor_workers", 1)
    monkeypatch.setattr(skill_scanner, "_scan_executor_slots", slot)
    monkeypatch.setattr(skill_scanner, "_scan_cache", {})

    result = skill_scanner.scan_skill_directory(skill_dir, timeout=0.01)

    assert result is None
    assert submitted_paths == []


@pytest.mark.asyncio
async def test_async_scan_bridge_does_not_block_event_loop(
    monkeypatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "slow"
    skill_dir.mkdir()

    def slow_scan(*_args, **_kwargs):
        time.sleep(0.06)

    monkeypatch.setattr(skill_scanner, "scan_skill_directory", slow_scan)
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        for _ in range(3):
            ticks += 1
            await asyncio.sleep(0.02)

    await asyncio.gather(
        skill_scanner.scan_skill_directory_async(skill_dir),
        heartbeat(),
    )
    assert ticks == 3
