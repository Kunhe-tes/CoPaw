# -*- coding: utf-8 -*-
"""Runtime worker boundaries for responsiveness-critical state work."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_runtime_state_work(
    func: Callable[..., T],
    /,
    *args,
    **kwargs,
) -> T:
    """Run responsiveness-critical runtime-state work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)
