# -*- coding: utf-8 -*-
"""Cancellation must survive discovery failures and keep the loop responsive."""

# Workers span async awaits; each test explicitly kills and waits in finally.
# pylint: disable=consider-using-with

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import threading
import time

import psutil
import pytest

from swe.app.subagents import (
    BackgroundSubAgentScope,
    BackgroundSubAgentSupervisor,
    DelegationSpec,
    PerRunSubAgentRunStore,
    PermissionPolicy,
    SubAgentDefinition,
)
from swe.app.subagents.supervisor import _ActiveRun


async def _register(supervisor, tmp_path, worker):
    scope = BackgroundSubAgentScope(
        tenant_id="test",
        agent_id="agent",
        run_store_dir=tmp_path / "runs",
    )
    store = PerRunSubAgentRunStore(scope.run_store_dir)
    record = await store.create(
        DelegationSpec(name="test", objective="Test cancellation"),
        SubAgentDefinition(
            name="test",
            description="test",
            instruction="test",
        ),
        PermissionPolicy.readonly(),
    )
    await store.mark_running(record.run_id, worker_pid=worker.pid)
    supervisor._active_for_scope(scope)[record.run_id] = _ActiveRun(
        scope=scope,
        process=worker,
        stderr_log_path=tmp_path / "stderr.log",
    )
    return scope, store, record.run_id


def _stop(worker):
    if worker.poll() is None:
        os.killpg(worker.pid, signal.SIGKILL)
    worker.wait(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [PermissionError("denied"), psutil.AccessDenied(123)],
)
async def test_discovery_failure_still_terminates_worker(
    tmp_path,
    monkeypatch,
    caplog,
    error,
):
    worker = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    try:
        from swe.app.subagents import supervisor as module

        supervisor = BackgroundSubAgentSupervisor(cancel_grace_seconds=0.2)
        scope, store, run_id = await _register(supervisor, tmp_path, worker)

        def denied(*args, **kwargs):
            raise error

        monkeypatch.setattr(psutil.Process, "children", denied)
        monkeypatch.setattr(
            module.logger,
            "handlers",
            [*module.logger.handlers, caplog.handler],
        )
        with caplog.at_level(logging.WARNING):
            result = await supervisor.cancel(scope, run_id)
        assert result.status == "cancelled"
        assert worker.poll() is not None
        assert (await store.get(run_id)).status == "cancelled"
        assert "background_subagent_descendant_discovery_failed" in caplog.text
        assert "descendant_cleanup=incomplete" in caplog.text
    finally:
        _stop(worker)


@pytest.mark.asyncio
@pytest.mark.parametrize("deny_discovery", [False, True])
async def test_real_descendant_wait_does_not_block_event_loop(
    tmp_path,
    monkeypatch,
    caplog,
    deny_discovery,
):
    from swe.app.subagents import supervisor as module

    discovery_errors = []
    original_children = psutil.Process.children

    def discover(process, *args, **kwargs):
        try:
            if deny_discovery:
                raise PermissionError("process discovery denied")
            return original_children(process, *args, **kwargs)
        except (OSError, psutil.AccessDenied) as exc:
            discovery_errors.append(exc)
            raise

    monkeypatch.setattr(psutil.Process, "children", discover)
    monkeypatch.setattr(
        module.logger,
        "handlers",
        [*module.logger.handlers, caplog.handler],
    )
    marker = tmp_path / "child.pid"
    child_code = (
        "import os, signal, time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    worker_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
        "start_new_session=True); time.sleep(60)"
    )
    worker = subprocess.Popen(
        [sys.executable, "-c", worker_code],
        start_new_session=True,
    )
    child = None
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert marker.exists()
        child = psutil.Process(int(marker.read_text()))
        supervisor = BackgroundSubAgentSupervisor(cancel_grace_seconds=0.5)
        scope, _, run_id = await _register(supervisor, tmp_path, worker)
        beats = []

        async def heartbeat():
            while True:
                beats.append(time.monotonic())
                await asyncio.sleep(0.01)

        ticker = asyncio.create_task(heartbeat())
        await asyncio.sleep(0)
        try:
            result = await supervisor.cancel(scope, run_id)
            await asyncio.sleep(0.02)
            assert result.status == "cancelled"
            assert worker.poll() is not None
            gaps = [right - left for left, right in zip(beats, beats[1:])]
            assert max(gaps) < 0.2
            if discovery_errors:
                assert "descendant_cleanup=incomplete" in caplog.text
            else:
                assert (
                    not child.is_running()
                    or child.status() == psutil.STATUS_ZOMBIE
                )
        finally:
            ticker.cancel()
            await asyncio.gather(ticker, return_exceptions=True)
    finally:
        if child is not None:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        _stop(worker)


@pytest.mark.asyncio
async def test_cancel_retains_handle_during_cleanup_and_survives_caller_cancel(
    tmp_path,
    monkeypatch,
):
    worker = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    entered, release = threading.Event(), threading.Event()
    calls = []
    supervisor = BackgroundSubAgentSupervisor()
    scope, store, run_id = await _register(supervisor, tmp_path, worker)

    def cleanup(process):
        calls.append(process.pid)
        _stop(process)
        entered.set()
        if not release.wait(2):
            raise RuntimeError("cleanup was blocked by the event loop")

    monkeypatch.setattr(supervisor, "_terminate_process_group", cleanup)
    waiter = asyncio.create_task(supervisor.wait_for_run(scope, run_id))
    await asyncio.sleep(0)
    first = asyncio.create_task(supervisor.cancel(scope, run_id))
    second = None
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        assert supervisor.is_manageable(scope, run_id)
        assert not waiter.done()
        assert (await supervisor.get(scope, run_id)).status == "running"
        assert supervisor.is_manageable(scope, run_id)
        second = asyncio.create_task(supervisor.cancel(scope, run_id))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert supervisor.is_manageable(scope, run_id)
        release.set()
        assert (await second).status == "cancelled"
        assert (await waiter).status == "cancelled"
        assert calls == [worker.pid]
        assert not supervisor.is_manageable(scope, run_id)
        assert (await store.get(run_id)).status == "cancelled"
    finally:
        release.set()
        await asyncio.gather(
            first,
            waiter,
            *([second] if second is not None else []),
            return_exceptions=True,
        )
        _stop(worker)


@pytest.mark.asyncio
async def test_cleanup_failure_retains_handle_and_cancel_can_retry(
    tmp_path,
    monkeypatch,
):
    worker = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    supervisor = BackgroundSubAgentSupervisor()
    scope, store, run_id = await _register(supervisor, tmp_path, worker)

    def incomplete(process):
        _stop(process)
        raise PermissionError("descendant cleanup denied")

    try:
        monkeypatch.setattr(supervisor, "_terminate_process_group", incomplete)
        with pytest.raises(PermissionError, match="descendant cleanup denied"):
            await supervisor.cancel(scope, run_id)
        assert (await supervisor.get(scope, run_id)).status == "running"
        assert supervisor.is_manageable(scope, run_id)
        monkeypatch.setattr(supervisor, "_terminate_process_group", _stop)
        assert (await supervisor.cancel(scope, run_id)).status == "cancelled"
        assert not supervisor.is_manageable(scope, run_id)
        assert (await store.get(run_id)).status == "cancelled"
    finally:
        _stop(worker)


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_before_cancel", [False, True])
@pytest.mark.parametrize(
    "cleanup_error",
    [
        PermissionError("descendant cleanup denied"),
        subprocess.TimeoutExpired("cleanup", 1),
    ],
)
async def test_failed_cleanup_waiters_return_persisted_state(
    tmp_path,
    monkeypatch,
    wait_before_cancel,
    cleanup_error,
):
    from swe.agents.tools.subagent_background import _wake_goal_after_subagent

    worker = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    supervisor = BackgroundSubAgentSupervisor()
    scope, store, run_id = await _register(supervisor, tmp_path, worker)
    entered, release = threading.Event(), threading.Event()

    def incomplete(process):
        _stop(process)
        entered.set()
        if not release.wait(5):
            raise RuntimeError("test cleanup gate timed out")
        raise cleanup_error

    monkeypatch.setattr(supervisor, "_terminate_process_group", incomplete)
    waiters = []
    cancel = None
    try:
        if wait_before_cancel:
            waiters.append(
                asyncio.create_task(supervisor.wait_for_run(scope, run_id)),
            )
            await asyncio.sleep(0)
        cancel = asyncio.create_task(supervisor.cancel(scope, run_id))
        assert await asyncio.to_thread(entered.wait, 5)
        if not wait_before_cancel:
            waiters.append(
                asyncio.create_task(supervisor.wait_for_run(scope, run_id)),
            )
        goal_waiter = asyncio.create_task(
            _wake_goal_after_subagent(
                supervisor=supervisor,
                scope=scope,
                goal_id="test-goal",
                run_id=run_id,
            ),
        )
        waiters.append(goal_waiter)
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(type(cleanup_error)):
            await cancel
        persisted = await store.get(run_id)
        assert (await waiters[0]) == persisted
        assert await goal_waiter is None
        assert persisted.status == "running"
        assert supervisor.is_manageable(scope, run_id)
        # A waiter arriving after the failed cancellation sees the same state.
        assert await supervisor.wait_for_run(scope, run_id) == persisted
    finally:
        release.set()
        await asyncio.gather(
            *waiters,
            *([cancel] if cancel is not None else []),
            return_exceptions=True,
        )
        _stop(worker)
