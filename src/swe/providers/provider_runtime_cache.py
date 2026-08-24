# -*- coding: utf-8 -*-
"""Scope-keyed runtime cache primitives for provider state."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class ProviderRuntimeCache:
    """Cache scope state while coalescing concurrent initialization/refresh."""

    def __init__(self, freshness_ttl_seconds: float = 300.0) -> None:
        self.freshness_ttl_seconds = freshness_ttl_seconds
        self._values: dict[str, Any] = {}
        self._builds: dict[str, asyncio.Future[Any]] = {}
        self._refreshes: dict[str, asyncio.Future[None]] = {}
        self._freshness_due: set[str] = set()
        self._next_freshness_check_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        scope: str,
        build: Callable[[], Awaitable[T]],
    ) -> T:
        async with self._lock:
            if scope in self._values:
                return self._values[scope]
            future = self._builds.get(scope)
            if future is None:
                future = asyncio.ensure_future(build())
                self._builds[scope] = future
        try:
            value = await asyncio.shield(future)
        except BaseException:
            if future.done():
                async with self._lock:
                    if self._builds.get(scope) is future:
                        self._builds.pop(scope, None)
            raise
        async with self._lock:
            self._values[scope] = value
            if self._builds.get(scope) is future:
                self._builds.pop(scope, None)
        return value

    def invalidate(self, scope: str) -> None:
        self._values.pop(scope, None)
        self.mark_freshness_due(scope)

    def mark_freshness_due(self, scope: str) -> None:
        self._freshness_due.add(scope)
        self._next_freshness_check_at[scope] = 0.0

    async def refresh_if_due(
        self,
        scope: str,
        refresh: Callable[[], Awaitable[None] | None],
    ) -> None:
        async with self._lock:
            if (
                scope not in self._freshness_due
                or time.monotonic()
                < self._next_freshness_check_at.get(scope, float("inf"))
            ):
                return
            future = self._refreshes.get(scope)
            if future is None:
                result = refresh()
                if inspect.isawaitable(result):
                    future = asyncio.ensure_future(result)
                else:
                    future = asyncio.get_running_loop().create_future()
                    future.set_result(None)
                self._refreshes[scope] = future
        try:
            await asyncio.shield(future)
        except BaseException:
            if future.done():
                async with self._lock:
                    if self._refreshes.get(scope) is future:
                        self._refreshes.pop(scope, None)
            raise
        async with self._lock:
            self._freshness_due.discard(scope)
            self._next_freshness_check_at[scope] = (
                time.monotonic() + self.freshness_ttl_seconds
            )
            if self._refreshes.get(scope) is future:
                self._refreshes.pop(scope, None)
