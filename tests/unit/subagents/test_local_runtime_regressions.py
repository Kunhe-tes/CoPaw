# -*- coding: utf-8 -*-
"""Concurrency, scope, cancellation and cross-process state regressions."""

from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import psutil
import pytest

from swe.app.subagents import (
    AgentResult,
    BackgroundSubAgentScope,
    BackgroundSubAgentStartBlocked,
    BackgroundSubAgentSupervisor,
    DelegationSpec,
    PerRunSubAgentRunStore,
    PermissionPolicy,
    SubAgentDefinition,
)
from swe.app.subagents.models import SubAgentLaunchDiagnostics
from swe.app.subagents.supervisor import _ActiveRun
from swe.config.config import AgentProfileConfig


def _definition():
    return SubAgentDefinition(
        name="test-expert",
        description="Test expert",
        instruction="Inspect",
    )


def _spec():
    return DelegationSpec(name="test-expert", objective="Inspect")


class FakeProcess:
    pid = 99999999
    returncode = None

    def poll(self):
        return self.returncode


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    from swe.app.subagents import supervisor as module

    monkeypatch.setattr(
        module,
        "capture_launch_dependencies",
        lambda **kwargs: ([], None, SubAgentLaunchDiagnostics()),
    )
    monkeypatch.setattr(
        module,
        "capture_model_launch_snapshot",
        lambda **kwargs: (None, None),
    )
    config = AgentProfileConfig(
        id="agent",
        name="Test",
        workspace_dir=str(tmp_path),
    )
    supervisor = BackgroundSubAgentSupervisor(
        popen_factory=lambda *a, **k: FakeProcess(),
    )
    return supervisor, config


def _scope(root):
    return BackgroundSubAgentScope(
        tenant_id="alice",
        agent_id="agent",
        run_store_dir=root / "runs",
    )


async def _start(runtime, scope):
    supervisor, config = runtime
    return await supervisor.start(
        scope=scope,
        spec=_spec(),
        definition=_definition(),
        parent_agent_config=config,
        workspace_dir=Path(config.workspace_dir),
    )


@pytest.mark.asyncio
async def test_concurrent_starts_reserve_capacity_before_snapshot(
    runtime,
    tmp_path,
    monkeypatch,
):
    from swe.app.subagents import supervisor as module

    gate = asyncio.Event()
    original = asyncio.to_thread

    async def gated_thread(function, *args, **kwargs):
        if function is module.capture_launch_dependencies:
            await gate.wait()
        return await original(function, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", gated_thread)
    tasks = [
        asyncio.create_task(_start(runtime, _scope(tmp_path)))
        for _ in range(3)
    ]
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*tasks)
    assert sum(item.status == "running" for item in results) == 2
    assert (
        sum(
            isinstance(item, BackgroundSubAgentStartBlocked)
            for item in results
        )
        == 1
    )


@pytest.mark.asyncio
async def test_failed_start_releases_capacity(runtime, tmp_path, monkeypatch):
    from swe.app.subagents import supervisor as module

    supervisor, _ = runtime
    supervisor._max_running_per_scope = 1

    def fail(**kwargs):
        raise OSError("snapshot failed")

    with monkeypatch.context() as patcher:
        patcher.setattr(module, "capture_launch_dependencies", fail)
        assert (await _start(runtime, _scope(tmp_path))).status == "failed"
    assert (await _start(runtime, _scope(tmp_path))).status == "running"


@pytest.mark.asyncio
async def test_cancelled_start_releases_capacity(
    runtime,
    tmp_path,
    monkeypatch,
):
    from swe.app.subagents import supervisor as module

    supervisor, _ = runtime
    supervisor._max_running_per_scope = 1
    entered = asyncio.Event()
    original = asyncio.to_thread

    async def pause_snapshot(function, *args, **kwargs):
        if function is module.capture_launch_dependencies:
            entered.set()
            await asyncio.Event().wait()
        return await original(function, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(asyncio, "to_thread", pause_snapshot)
        task = asyncio.create_task(_start(runtime, _scope(tmp_path)))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (await _start(runtime, _scope(tmp_path))).status == "running"


@pytest.mark.asyncio
async def test_popen_failure_releases_capacity(runtime, tmp_path, monkeypatch):
    supervisor, _ = runtime
    supervisor._max_running_per_scope = 1

    def fail(*args, **kwargs):
        raise OSError("worker launch failed")

    with monkeypatch.context() as patcher:
        patcher.setattr(supervisor, "_popen_factory", fail)
        assert (await _start(runtime, _scope(tmp_path))).status == "failed"
    assert (await _start(runtime, _scope(tmp_path))).status == "running"


@pytest.mark.asyncio
async def test_different_source_directories_have_independent_capacity(
    runtime,
    tmp_path,
):
    runtime[0]._max_running_per_scope = 1
    a = await _start(runtime, _scope(tmp_path / "source-a"))
    b = await _start(runtime, _scope(tmp_path / "source-b"))
    assert a.status == b.status == "running"


@pytest.mark.asyncio
async def test_other_source_cannot_reap_a_handle(runtime, tmp_path):
    supervisor, _ = runtime
    a, b = _scope(tmp_path / "source-a"), _scope(tmp_path / "source-b")
    record = await _start(runtime, a)
    supervisor._active_for_scope(a)[record.run_id].process.returncode = 0
    await supervisor.wait(b, timeout_ms=0)
    assert supervisor.is_manageable(a, record.run_id)
    await supervisor.wait(a, timeout_ms=0)
    assert (await supervisor.get(a, record.run_id)).status == "failed"


@pytest.mark.asyncio
async def test_other_source_cannot_cancel_a_handle(
    runtime,
    tmp_path,
    monkeypatch,
):
    supervisor, _ = runtime
    a, b = _scope(tmp_path / "source-a"), _scope(tmp_path / "source-b")
    first = await _start(runtime, a)
    second = await _start(runtime, b)
    terminated = []
    monkeypatch.setattr(
        supervisor,
        "_terminate_process_group",
        terminated.append,
    )

    assert await supervisor.cancel(b, first.run_id) is None
    assert supervisor.is_manageable(a, first.run_id)
    assert terminated == []
    assert (await supervisor.cancel(a, first.run_id)).status == "cancelled"
    assert len(terminated) == 1
    assert (await supervisor.get(b, second.run_id)).status == "running"


def _update_process(directory, run_id, operation, read, release, done):
    store = PerRunSubAgentRunStore(Path(directory))
    if read is not None:
        write = store._write

        def delayed(record):
            read.set()
            if not release.wait(10):
                raise RuntimeError("update barrier timed out")
            write(record)

        store._write = delayed
    arguments = {
        "mark_running": {"worker_pid": 123},
        "record_turns": {"turns_used": 2},
        "record_connected_mcps": {"names": ["test"]},
        "record_resolved_model": {
            "value": {"provider_id": "test", "model": "test"},
        },
        "mark_worker_exited": {"exit_code": 0},
        "finish": {
            "result": AgentResult(
                task_id="test",
                agent_run_id=run_id,
                agent_name="test-expert",
                status="completed",
                summary="Preserve this result",
            ),
        },
    }
    asyncio.run(getattr(store, operation)(run_id, **arguments[operation]))
    done.set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        "mark_running",
        "record_turns",
        "record_connected_mcps",
        "record_resolved_model",
        "mark_worker_exited",
    ],
)
async def test_stale_process_update_cannot_erase_completed_result(
    tmp_path,
    operation,
):
    store = PerRunSubAgentRunStore(tmp_path)
    record = await store.create(
        _spec(),
        _definition(),
        PermissionPolicy.readonly(),
    )
    await store.mark_running(record.run_id, worker_pid=123)
    context = multiprocessing.get_context("spawn")
    read, release, first_done, finish_done = [
        context.Event() for _ in range(4)
    ]
    first = context.Process(
        target=_update_process,
        args=(
            str(tmp_path),
            record.run_id,
            operation,
            read,
            release,
            first_done,
        ),
    )
    second = context.Process(
        target=_update_process,
        args=(
            str(tmp_path),
            record.run_id,
            "finish",
            None,
            release,
            finish_done,
        ),
    )
    first.start()
    try:
        assert await asyncio.to_thread(read.wait, 10)
        second.start()
        # Without a transaction the finish races ahead of the paused writer.
        await asyncio.to_thread(finish_done.wait, 1.5)
        release.set()
        await asyncio.to_thread(first.join, 10)
        await asyncio.to_thread(second.join, 10)
        assert first.exitcode == second.exitcode == 0
        result = await store.get(record.run_id)
        assert result.status == "completed"
        assert result.result.summary == "Preserve this result"
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                if process.is_alive():
                    process.kill()
                process.join(5)


def _alive(process):
    try:
        return (
            process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        )
    except psutil.NoSuchProcess:
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("ignore_term", [False, True])
async def test_cancel_stops_shell_in_a_separate_session(tmp_path, ignore_term):
    marker = tmp_path / "shell.json"
    script = """
import json, os, signal, subprocess, sys, time
if sys.argv[2] == 'True':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen(['/bin/sh', '-c', "trap '' TERM; sleep 60"], start_new_session=True)
with open(sys.argv[1], 'w') as stream:
    json.dump({'pid': child.pid, 'pgid': os.getpgid(child.pid)}, stream)
time.sleep(60)
"""
    worker = subprocess.Popen(
        [sys.executable, "-c", script, str(marker), str(ignore_term)],
        start_new_session=True,
    )
    children = []
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert marker.exists()
        child = psutil.Process(json.loads(marker.read_text())["pid"])
        children = psutil.Process(worker.pid).children(recursive=True)
        assert os.getpgid(worker.pid) != os.getpgid(child.pid)
        scope = _scope(tmp_path)
        store = PerRunSubAgentRunStore(scope.run_store_dir)
        record = await store.create(
            _spec(),
            _definition(),
            PermissionPolicy.readonly(),
        )
        await store.mark_running(record.run_id, worker_pid=worker.pid)
        supervisor = BackgroundSubAgentSupervisor(cancel_grace_seconds=0.2)
        supervisor._active_for_scope(scope)[record.run_id] = _ActiveRun(
            scope=scope,
            process=worker,
            stderr_log_path=tmp_path / "stderr.log",
        )
        cancelled = await supervisor.cancel(scope, record.run_id)
        assert cancelled.status == "cancelled"
        assert worker.poll() is not None
        assert not _alive(child)
        assert all(not _alive(process) for process in children)
    finally:
        for process in children:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        if worker.poll() is None:
            os.killpg(worker.pid, signal.SIGKILL)
        worker.wait(timeout=5)
