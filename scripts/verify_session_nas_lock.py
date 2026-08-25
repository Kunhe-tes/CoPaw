#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the NAS session lock and atomic JSON revision contract.

This is an operator-side check. It does not touch application session files;
it only creates ``.verification.json`` below the directory supplied by the
operator.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import multiprocessing as mp
import os
import tempfile
from pathlib import Path


def _lock_path(root: Path) -> Path:
    return root / ".verification.json.lock"


def _acquire(path: Path, non_blocking: bool) -> object:
    handle = path.open("a+")
    flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if non_blocking else 0)
    fcntl.flock(handle.fileno(), flags)
    return handle


def _holder(
    root: str,
    ready: mp.synchronize.Event,
    release: mp.synchronize.Event,
) -> None:
    with _acquire(_lock_path(Path(root)), non_blocking=False):
        ready.set()
        release.wait(30)


def _verify_contention(root: Path) -> None:
    ready = mp.Event()
    release = mp.Event()
    process = mp.Process(target=_holder, args=(str(root), ready, release))
    process.start()
    try:
        if not ready.wait(10):
            raise RuntimeError("lock holder did not enter within 10 seconds")
        try:
            with _acquire(_lock_path(root), non_blocking=True):
                raise RuntimeError("second worker unexpectedly acquired lock")
        except OSError as exc:
            if exc.errno not in {
                errno.EACCES,
                errno.EAGAIN,
                errno.EWOULDBLOCK,
            }:
                raise
        release.set()
        process.join(10)
        if process.exitcode != 0:
            raise RuntimeError(f"lock holder exited with {process.exitcode}")
        with _acquire(_lock_path(root), non_blocking=True):
            pass
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()


def _atomic_commit(path: Path, state: dict[str, int]) -> None:
    encoded = json.dumps(state, separators=(",", ":"), sort_keys=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".verification.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(encoded)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
        directory_fd = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def _verify_revisions(root: Path, count: int) -> None:
    path = root / ".verification.json"
    lock = _lock_path(root)
    with _acquire(lock, non_blocking=False):
        for revision in range(1, count + 1):
            state = {"revision": revision}
            _atomic_commit(path, state)
            with path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if loaded != state:
                raise RuntimeError(
                    f"unexpected state at revision {revision}: {loaded!r}",
                )
    path.unlink(missing_ok=True)
    lock.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--revisions", type=int, default=1000)
    args = parser.parse_args()
    if args.revisions <= 0:
        parser.error("--revisions must be positive")
    args.session_dir.mkdir(parents=True, exist_ok=True)
    _verify_contention(args.session_dir)
    _verify_revisions(args.session_dir, args.revisions)
    print(f"NAS session lock verification passed: {args.session_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
