# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path

import pytest

from swe.agents.utils import file_handling


@pytest.mark.asyncio
async def test_base64_persistence_runs_outside_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = file_handling._download_file_from_base64_sync

    def slow_sync(*args, **kwargs):
        time.sleep(0.08)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        file_handling,
        "_download_file_from_base64_sync",
        slow_sync,
    )
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        for _ in range(4):
            ticks += 1
            await asyncio.sleep(0.02)

    payload = base64.b64encode(b"hello").decode()
    result, _ = await asyncio.gather(
        file_handling.download_file_from_base64(
            payload,
            "x.txt",
            str(tmp_path),
        ),
        heartbeat(),
    )

    assert ticks == 4
    assert Path(result).read_bytes() == b"hello"
    assert not list(tmp_path.glob("*.part-*"))


@pytest.mark.asyncio
async def test_base64_size_limit_is_enforced(tmp_path: Path) -> None:
    payload = base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode()
    with pytest.raises(ValueError, match="10 MiB"):
        await file_handling.download_file_from_base64(
            payload,
            "oversized.bin",
            str(tmp_path),
        )


@pytest.mark.asyncio
async def test_remote_download_rejects_non_http_scheme(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported media URL scheme"):
        await file_handling.download_file_from_url(
            "ftp://example.test/file.bin",
            download_dir=str(tmp_path),
        )


@pytest.mark.asyncio
async def test_media_worker_executor_is_bounded(monkeypatch) -> None:
    active = 0
    peak = 0

    def worker() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        time.sleep(0.03)
        active -= 1

    await asyncio.gather(
        *(file_handling._run_media_worker(worker) for _ in range(8)),
    )
    assert peak <= file_handling._MEDIA_WORKER_COUNT
