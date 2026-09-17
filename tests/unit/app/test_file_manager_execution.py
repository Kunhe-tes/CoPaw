# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import threading

import pytest

from swe.app.file_manager import FileManagerPathError
from swe.app.file_manager_execution import (
    run_file_manager_mutation,
    run_file_manager_read,
)


@pytest.mark.asyncio
async def test_read_lane_returns_synchronous_result() -> None:
    result = await run_file_manager_read(lambda value: value + 1, 41)

    assert result == 42


@pytest.mark.asyncio
async def test_mutation_lane_preserves_file_manager_exception() -> None:
    error = FileManagerPathError("denied")

    def raise_error() -> None:
        raise error

    with pytest.raises(FileManagerPathError) as raised:
        await run_file_manager_mutation(raise_error)

    assert raised.value is error


@pytest.mark.asyncio
async def test_mutation_lane_limits_parallel_work() -> None:
    started = threading.Event()
    release = threading.Event()
    active = 0
    maximum = 0
    lock = threading.Lock()

    def blocking_call() -> None:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                started.set()
        release.wait(timeout=2)
        with lock:
            active -= 1

    tasks = [
        asyncio.create_task(run_file_manager_mutation(blocking_call))
        for _ in range(3)
    ]
    assert await asyncio.to_thread(started.wait, 2)
    await asyncio.sleep(0)
    assert maximum == 2
    release.set()
    await asyncio.gather(*tasks)
