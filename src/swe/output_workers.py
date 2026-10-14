# -*- coding: utf-8 -*-
"""Bound large tool-output work independently of runtime-state workers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from functools import partial
import threading
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="swe-output")
_SLOTS = threading.BoundedSemaphore(8)


async def run_output_work(
    func: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Submit only with a slot; cancellation never releases running work."""
    slots = _SLOTS
    # The worker releases this permit, including after request cancellation.
    # pylint: disable=consider-using-with
    while not slots.acquire(blocking=False):
        await asyncio.sleep(0.005)
    context = copy_context()
    callback = partial(func, *args, **kwargs)

    def run() -> T:
        try:
            return context.run(callback)
        finally:
            slots.release()

    try:
        future = _EXECUTOR.submit(run)
    except BaseException:
        slots.release()
        raise
    wrapped = asyncio.wrap_future(future)

    def completed(done: asyncio.Future[T]) -> None:
        if not done.cancelled():
            done.exception()

    wrapped.add_done_callback(completed)
    return await asyncio.shield(wrapped)
