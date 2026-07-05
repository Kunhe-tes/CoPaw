# -*- coding: utf-8 -*-
"""Background SubAgent supervisor tests."""

from __future__ import annotations

import signal
from pathlib import Path

import pytest

from swe.app.subagents import (
    AgentRegistry,
    BackgroundSubAgentScope,
    BackgroundSubAgentStartBlocked,
    BackgroundSubAgentSupervisor,
    DelegationSpec,
    PerRunSubAgentRunStore,
    PermissionPolicy,
    builtin_definition_provider,
)
from swe.config.config import AgentProfileConfig


class _FakeProcess:
    def __init__(self, pid: int = 4321):
        self.pid = pid
        self.returncode: int | None = None
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = -signal.SIGTERM
        return self.returncode


class _FakePopenFactory:
    def __init__(self):
        self.processes: list[_FakeProcess] = []
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        process = _FakeProcess(pid=4321 + len(self.processes))
        self.processes.append(process)
        self.commands.append(list(command))
        return process


def _scope(tmp_path: Path) -> BackgroundSubAgentScope:
    return BackgroundSubAgentScope(
        tenant_id="tenant-1",
        agent_id="agent-1",
        run_store_dir=tmp_path / "subagent_runs",
    )


def _spec() -> DelegationSpec:
    return DelegationSpec(
        task_id="task-1",
        parent_thread_id="session-1",
        name="plan-researcher",
        objective="Inspect supervisor behavior",
    )


def _agent_config(tmp_path: Path) -> AgentProfileConfig:
    return AgentProfileConfig(
        id="agent-1",
        name="Agent",
        workspace_dir=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_start_blocks_when_concurrency_limit_reached(tmp_path):
    popen_factory = _FakePopenFactory()
    supervisor = BackgroundSubAgentSupervisor(
        max_running_per_scope=1,
        popen_factory=popen_factory,
        registry=AgentRegistry([builtin_definition_provider()]),
    )
    scope = _scope(tmp_path)

    first = await supervisor.start(
        scope=scope,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
    )
    second = await supervisor.start(
        scope=scope,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
    )

    run_files = [
        path
        for path in scope.run_store_dir.glob("subagent-*.json")
        if not path.name.endswith(".launch.json")
    ]
    assert first.status == "running"
    assert isinstance(second, BackgroundSubAgentStartBlocked)
    assert second.status == "blocked"
    assert second.reason == "background_subagent_concurrency_limit"
    assert second.limit == 1
    assert second.active_run_ids == [first.run_id]
    assert len(run_files) == 1


@pytest.mark.asyncio
async def test_wait_lazy_reaps_worker_without_result(tmp_path):
    popen_factory = _FakePopenFactory()
    supervisor = BackgroundSubAgentSupervisor(
        max_running_per_scope=1,
        popen_factory=popen_factory,
    )
    scope = _scope(tmp_path)
    started = await supervisor.start(
        scope=scope,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
    )
    popen_factory.processes[0].returncode = 1

    snapshot = await supervisor.wait(scope, timeout_ms=1)
    record = await PerRunSubAgentRunStore(scope.run_store_dir).get(
        started.run_id,
    )

    assert snapshot.terminal_runs
    assert snapshot.terminal_runs[0].status == "failed"
    assert record is not None
    assert record.status == "failed"
    assert record.worker is not None
    assert record.worker.exit_code == 1
    assert record.errors[-1].code == "worker_exited_without_result"


@pytest.mark.asyncio
async def test_cancel_terminates_process_group(
    monkeypatch,
    tmp_path,
):
    from swe.app.subagents import supervisor as supervisor_module

    signals: list[int] = []
    popen_factory = _FakePopenFactory()
    supervisor = BackgroundSubAgentSupervisor(
        max_running_per_scope=1,
        popen_factory=popen_factory,
    )
    scope = _scope(tmp_path)
    started = await supervisor.start(
        scope=scope,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
    )

    monkeypatch.setattr(supervisor_module.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        supervisor_module.os,
        "killpg",
        lambda _pgid, sig: signals.append(sig),
    )

    response = await supervisor.cancel(scope, started.run_id)

    assert response.status == "cancelled"
    assert signals == [signal.SIGTERM]


@pytest.mark.asyncio
async def test_start_failure_uses_structured_worker_start_error(tmp_path):
    def _raising_popen(command, **kwargs):
        raise OSError("no worker")

    supervisor = BackgroundSubAgentSupervisor(
        max_running_per_scope=1,
        popen_factory=_raising_popen,
    )
    scope = _scope(tmp_path)

    response = await supervisor.start(
        scope=scope,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
    )

    assert response.status == "failed"
    assert response.errors[-1].code == "worker_start_failed"
