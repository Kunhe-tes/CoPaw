# -*- coding: utf-8 -*-
"""Tests for service heartbeat scheduling and runtime isolation."""

from __future__ import annotations

import asyncio
import threading

import pytest

from swe.app import service_heartbeat as service_heartbeat_module
from swe.app.service_heartbeat import ServiceHeartbeatManager


class _ServiceHeartbeatConfig:
    enabled = True
    url = "http://heartbeat.test/register"
    interval_seconds = 30
    instance_port = 8080
    service_name = "swe"
    weight = 1


@pytest.mark.asyncio
async def test_heartbeat_loop_keeps_fixed_rate_when_send_is_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow heartbeat request should not be added to the next interval."""
    service_heartbeat_module._shutdown_requested = False
    manager = ServiceHeartbeatManager(_ServiceHeartbeatConfig())
    now = 0.0
    send_times: list[float] = []
    sleep_delays: list[float] = []

    async def fake_send_heartbeat(enabled: bool = True) -> bool:
        nonlocal now
        assert enabled is True
        send_times.append(now)
        now += 10.0
        if len(send_times) >= 2:
            manager._running = False
        return True

    async def fake_sleep(delay: float) -> None:
        nonlocal now
        if len(send_times) >= 2:
            raise asyncio.CancelledError
        sleep_delays.append(delay)
        now += delay

    manager._send_heartbeat = fake_send_heartbeat  # type: ignore[method-assign]
    manager._monotonic_time = lambda: now  # type: ignore[attr-defined]
    manager._sleep = fake_sleep  # type: ignore[attr-defined]
    monkeypatch.setattr(service_heartbeat_module.asyncio, "sleep", fake_sleep)

    manager._running = True
    await manager._heartbeat_loop()

    assert send_times == [0.0, 30.0]
    assert sleep_delays == [20.0]


@pytest.mark.asyncio
async def test_start_runs_heartbeat_loop_on_dedicated_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The heartbeat loop should not depend on the main application loop."""
    service_heartbeat_module._shutdown_requested = False
    manager = ServiceHeartbeatManager(_ServiceHeartbeatConfig())
    started = threading.Event()

    async def fake_heartbeat_loop() -> None:
        started.set()
        while manager._running:
            await asyncio.sleep(0.01)

    async def fake_send_heartbeat(enabled: bool = True) -> bool:
        return enabled

    monkeypatch.setattr(manager, "_heartbeat_loop", fake_heartbeat_loop)
    monkeypatch.setattr(manager, "_send_heartbeat", fake_send_heartbeat)
    monkeypatch.setattr(manager, "_register_shutdown_handlers", lambda: None)

    await manager.start()
    try:
        assert await asyncio.to_thread(started.wait, 1.0)
        assert manager._worker_thread is not None
        assert manager._worker_thread.is_alive()
        assert manager._worker_loop is not None
        assert manager._worker_loop is not asyncio.get_running_loop()
    finally:
        await manager.stop()
