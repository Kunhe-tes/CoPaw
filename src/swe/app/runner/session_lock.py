# -*- coding: utf-8 -*-
"""Async-compatible advisory locks for runner session files."""

from __future__ import annotations

import asyncio
import errno

from pathlib import Path
from typing import IO

try:
    import fcntl
except ImportError:  # pragma: no cover - Unix deployment contract
    fcntl = None


class SessionLockError(RuntimeError):
    """Raised when session file locking cannot be safely performed."""


class SessionLockTimeout(SessionLockError):
    """Raised when session file lock contention exceeds its bounded wait."""


class AsyncSessionFileLock:
    """Acquire an exclusive Unix advisory lock without blocking the event loop."""

    def __init__(
        self,
        lock_path: Path,
        *,
        timeout_seconds: float | None = None,
        poll_seconds: float = 0.05,
    ) -> None:
        self._lock_path = Path(lock_path)
        self._timeout_seconds = timeout_seconds
        self._poll_seconds = poll_seconds
        self._handle: IO[str] | None = None
        self._locked = False

    async def __aenter__(self) -> "AsyncSessionFileLock":
        if fcntl is None:
            raise SessionLockError("fcntl.flock is unavailable")

        try:
            self._handle = await asyncio.to_thread(self._open_lock_file)
            deadline = self._deadline()
            while True:
                try:
                    await self._attempt_lock()
                    return self
                except OSError as exc:
                    if not self._is_contention(exc):
                        raise SessionLockError(
                            "failed to acquire session lock: "
                            f"{self._lock_path}",
                        ) from exc
                    if (
                        deadline is not None
                        and asyncio.get_running_loop().time() >= deadline
                    ):
                        raise SessionLockTimeout(
                            "timed out acquiring session lock: "
                            f"{self._lock_path}",
                        ) from exc
                    await asyncio.sleep(self._poll_seconds)
        except BaseException:
            await self._release_and_close()
            raise

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self._release_and_close()

    def _deadline(self) -> float | None:
        if self._timeout_seconds is None:
            return None
        return asyncio.get_running_loop().time() + self._timeout_seconds

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
            raise SessionLockError("session lock file is not open")
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
            raise SessionLockError(
                f"failed to release session lock: {self._lock_path}",
            ) from exc
        finally:
            self._locked = False
            await asyncio.to_thread(handle.close)

    @staticmethod
    def _is_contention(exc: OSError) -> bool:
        return exc.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}


def get_session_lock_path(session_save_path: str) -> Path:
    session_path = Path(session_save_path)
    return session_path.with_name(f".{session_path.name}.lock")
