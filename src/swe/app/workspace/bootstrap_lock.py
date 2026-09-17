# -*- coding: utf-8 -*-
"""Async-compatible cross-process locks for tenant bootstrap."""

from __future__ import annotations

import asyncio
import errno
from pathlib import Path
from typing import IO

try:
    import fcntl
except ImportError:  # pragma: no cover - Unix deployment contract
    fcntl = None


class BootstrapLockTimeout(RuntimeError):
    """Raised when bootstrap lock contention exceeds its bounded wait."""


class BootstrapLockFailure(RuntimeError):
    """Raised when bootstrap locking cannot be safely performed."""


class AsyncFlock:
    """Acquire an exclusive Unix advisory lock without blocking the event loop."""

    def __init__(
        self,
        lock_path: Path,
        *,
        timeout_seconds: float = 30.0,
        poll_seconds: float = 0.05,
    ) -> None:
        self._lock_path = Path(lock_path)
        self._timeout_seconds = timeout_seconds
        self._poll_seconds = poll_seconds
        self._handle: IO[str] | None = None
        self._locked = False

    async def __aenter__(self) -> "AsyncFlock":
        """Acquire the lock or raise a typed failure."""
        if fcntl is None:
            raise BootstrapLockFailure("fcntl.flock is unavailable")

        try:
            self._handle = await asyncio.to_thread(self._open_lock_file)
            deadline = (
                asyncio.get_running_loop().time() + self._timeout_seconds
            )
            while True:
                try:
                    await self._attempt_lock()
                    return self
                except OSError as exc:
                    if not self._is_contention(exc):
                        raise BootstrapLockFailure(
                            f"failed to acquire bootstrap lock: {self._lock_path}",
                        ) from exc
                    if asyncio.get_running_loop().time() >= deadline:
                        raise BootstrapLockTimeout(
                            f"timed out acquiring bootstrap lock: {self._lock_path}",
                        ) from exc
                    await asyncio.sleep(self._poll_seconds)
        except BaseException:
            await self._release_and_close()
            raise

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """Release the lock and close its descriptor."""
        await self._release_and_close()

    def _open_lock_file(self) -> IO[str]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        return self._lock_path.open("a+", encoding="utf-8")

    async def _attempt_lock(self) -> None:
        task = asyncio.create_task(asyncio.to_thread(self._lock_once))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            loop = asyncio.get_running_loop()
            task.add_done_callback(
                lambda _: loop.create_task(self._release_and_close()),
            )
            raise

    def _lock_once(self) -> None:
        if self._handle is None:
            raise BootstrapLockFailure("bootstrap lock file is not open")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self._locked = True

    async def _release_and_close(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return

        try:
            if self._locked and fcntl is not None:
                await asyncio.to_thread(
                    fcntl.flock,
                    handle.fileno(),
                    fcntl.LOCK_UN,
                )
        except OSError as exc:
            raise BootstrapLockFailure(
                f"failed to release bootstrap lock: {self._lock_path}",
            ) from exc
        finally:
            self._locked = False
            await asyncio.to_thread(handle.close)

    @staticmethod
    def _is_contention(exc: OSError) -> bool:
        return exc.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}
