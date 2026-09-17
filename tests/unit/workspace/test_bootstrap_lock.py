# -*- coding: utf-8 -*-
"""Regression tests for cross-process tenant bootstrap locking."""

import asyncio
import errno
import multiprocessing
import os
import sys
from contextlib import contextmanager, suppress
from pathlib import Path
from queue import Empty
from typing import Iterator

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "src"))

try:
    import fcntl
except ImportError:  # pragma: no cover - Unix deployment contract
    fcntl = None

from swe.app.workspace.bootstrap_lock import (
    AsyncFlock,
    BootstrapLockFailure,
    BootstrapLockTimeout,
)


def _hold_lock(lock_path: str, ready, release) -> None:
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        ready.put(True)
        release.wait(timeout=5)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _held_by_other_process(lock_path: Path) -> Iterator[None]:
    if fcntl is None:  # pragma: no cover - Unix deployment contract
        pytest.skip("fcntl.flock is required by the deployment contract")
    context = multiprocessing.get_context("fork")
    ready = context.Queue()
    release = context.Event()
    process = context.Process(
        target=_hold_lock,
        args=(str(lock_path), ready, release),
    )
    process.start()
    try:
        assert ready.get(timeout=2) is True
        yield
    finally:
        release.set()
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)


@pytest.mark.asyncio
async def test_lock_timeout_is_not_treated_as_success(tmp_path: Path) -> None:
    lock_path = tmp_path / "scope-a" / ".bootstrap.lock"

    with _held_by_other_process(lock_path):
        lock = AsyncFlock(
            lock_path,
            timeout_seconds=0.02,
            poll_seconds=0.005,
        )
        with pytest.raises(BootstrapLockTimeout):
            async with lock:
                raise AssertionError("lock acquisition must not succeed")


@pytest.mark.asyncio
async def test_lock_wait_yields_to_event_loop(tmp_path: Path) -> None:
    lock_path = tmp_path / "scope-a" / ".bootstrap.lock"

    with _held_by_other_process(lock_path):
        acquire_task = asyncio.create_task(
            AsyncFlock(
                lock_path,
                timeout_seconds=1,
                poll_seconds=0.005,
            ).__aenter__(),
        )
        await asyncio.sleep(0)
        assert not acquire_task.done()
        acquire_task.cancel()
        with suppress(asyncio.CancelledError):
            await acquire_task


@pytest.mark.asyncio
async def test_unexpected_flock_error_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swe.app.workspace import bootstrap_lock

    def fail_flock(*_args) -> None:
        raise OSError(errno.EIO, "simulated lock I/O failure")

    monkeypatch.setattr(bootstrap_lock.fcntl, "flock", fail_flock)

    with pytest.raises(BootstrapLockFailure):
        async with AsyncFlock(tmp_path / ".bootstrap.lock"):
            raise AssertionError("lock acquisition must not succeed")
