# -*- coding: utf-8 -*-
"""Background SubAgent worker entrypoint tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.app.subagents import (
    AgentRegistry,
    AgentResult,
    DelegationSpec,
    PerRunSubAgentRunStore,
    PermissionPolicy,
    WorkerLaunchSpec,
    builtin_definition_provider,
)
from swe.config.config import AgentProfileConfig


def _definition():
    registry = AgentRegistry([builtin_definition_provider()])
    return registry.resolve("plan-researcher")


def _spec() -> DelegationSpec:
    return DelegationSpec(
        task_id="task-1",
        parent_thread_id="session-1",
        agent_name="plan-researcher",
        objective="Inspect worker behavior",
    )


def _agent_config(tmp_path: Path) -> AgentProfileConfig:
    return AgentProfileConfig(
        id="default",
        name="Default",
        workspace_dir=str(tmp_path),
    )


def _result(run_id: str) -> AgentResult:
    return AgentResult(
        task_id="task-1",
        agent_run_id=run_id,
        agent_name="plan-researcher",
        status="completed",
        summary="worker completed",
    )


async def _write_launch_spec(tmp_path: Path) -> tuple[Path, str, Path]:
    run_store_dir = tmp_path / "subagent_runs"
    store = PerRunSubAgentRunStore(run_store_dir)
    definition = _definition()
    record = await store.create(
        _spec(),
        definition,
        PermissionPolicy.readonly(),
    )
    launch = WorkerLaunchSpec(
        run_id=record.run_id,
        run_store_dir=str(run_store_dir),
        workspace_dir=str(tmp_path / "workspace"),
        parent_agent_config=_agent_config(tmp_path).model_dump(mode="json"),
        definition=definition,
        delegation_spec=record.spec,
        effective_policy=record.effective_policy,
        request_context={
            "session_id": "session-1",
            "OPENAI_API_KEY": "must-not-persist",
            "_hook_overlay_model": object(),
        },
        stderr_log_path=str(run_store_dir / f"{record.run_id}.stderr.log"),
    )
    launch_path = run_store_dir / f"{record.run_id}.launch.json"
    launch_path.write_text(
        json.dumps(launch.model_dump(mode="json")),
        encoding="utf-8",
    )
    return launch_path, record.run_id, run_store_dir


def test_launch_spec_filters_secret_like_context(tmp_path):
    spec = WorkerLaunchSpec(
        run_id="subagent-test",
        run_store_dir=str(tmp_path / "runs"),
        workspace_dir=str(tmp_path),
        parent_agent_config={
            **_agent_config(tmp_path).model_dump(mode="json"),
            "providers": {
                "OPENAI_API_KEY": "secret",
                "nested": {"client_secret": "secret"},
            },
        },
        definition=_definition(),
        delegation_spec=_spec(),
        effective_policy=PermissionPolicy.readonly(),
        request_context={
            "session_id": "session-1",
            "tenant_id": "tenant-1",
            "OPENAI_API_KEY": "secret",
            "SWE_PROVIDER_API_KEY": "secret",
        },
        OPENAI_API_KEY="secret",
    )

    payload = spec.model_dump_json()

    assert "session-1" in payload
    assert "tenant-1" in payload
    assert "OPENAI_API_KEY" not in payload
    assert "SWE_PROVIDER_API_KEY" not in payload
    assert "client_secret" not in payload
    assert "secret" not in payload


@pytest.mark.asyncio
async def test_worker_writes_terminal_result_from_runtime(
    monkeypatch,
    tmp_path,
):
    from swe.app.subagents import worker as worker_module

    class FakeRuntime:
        def __init__(self, store):
            self.store = store

        async def run(self, **kwargs):
            assert kwargs["run"].run_id == run_id
            assert kwargs["request_context"] == {"session_id": "session-1"}
            assert isinstance(
                kwargs["parent_agent_config"],
                AgentProfileConfig,
            )
            return _result(run_id)

    launch_path, run_id, run_store_dir = await _write_launch_spec(tmp_path)
    monkeypatch.setattr(worker_module, "SubAgentRuntime", FakeRuntime)

    exit_code = await worker_module.run_worker(launch_path)
    record = await PerRunSubAgentRunStore(run_store_dir).get(run_id)

    assert exit_code == 0
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    assert record.result.summary == "worker completed"


@pytest.mark.asyncio
async def test_worker_exception_writes_failed(monkeypatch, tmp_path):
    from swe.app.subagents import worker as worker_module

    class RaisingRuntime:
        def __init__(self, store):
            self.store = store

        async def run(self, **kwargs):
            raise RuntimeError("provider unavailable")

    launch_path, run_id, run_store_dir = await _write_launch_spec(tmp_path)
    monkeypatch.setattr(worker_module, "SubAgentRuntime", RaisingRuntime)

    exit_code = await worker_module.run_worker(launch_path)
    record = await PerRunSubAgentRunStore(run_store_dir).get(run_id)

    assert exit_code == 1
    assert record is not None
    assert record.status == "failed"
    assert record.errors
    assert "provider unavailable" in record.errors[-1].message
