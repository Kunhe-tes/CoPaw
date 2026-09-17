# -*- coding: utf-8 -*-
"""Bounded worker lanes for synchronous File Manager filesystem work."""

from __future__ import annotations

from functools import partial
from typing import Callable, ParamSpec, TypeVar

import anyio

P = ParamSpec("P")
T = TypeVar("T")

_READ_LIMITER = anyio.CapacityLimiter(8)
_MUTATION_LIMITER = anyio.CapacityLimiter(2)


async def _run(
    limiter: anyio.CapacityLimiter,
    function: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    return await anyio.to_thread.run_sync(
        partial(function, *args, **kwargs),
        limiter=limiter,
    )


async def run_file_manager_read(
    function: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run read-only filesystem work in its bounded worker lane."""
    return await _run(_READ_LIMITER, function, *args, **kwargs)


async def run_file_manager_mutation(
    function: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run mutation filesystem work in its bounded worker lane."""
    return await _run(_MUTATION_LIMITER, function, *args, **kwargs)
