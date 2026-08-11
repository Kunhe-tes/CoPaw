# -*- coding: utf-8 -*-
"""Background SubAgent worker entrypoint tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.app.subagents import (
    AgentRegistry,
    AgentResult,
    DefinitionMatchMetadata,
    DelegationSpec,
    PerRunSubAgentRunStore,
    PermissionPolicy,
    SubAgentStartRequest,
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
        name="plan-researcher",
        objective="Inspect worker behavior",
    )


def _agent_config(tmp_path: Path) -> AgentProfileConfig:
    return AgentProfileConfig(
        id="default",
        name="Default",
        workspace_dir=str(tmp_path),
    )


def _result(run_id: str, *, status: str = "completed") -> AgentResult:
    return AgentResult(
        task_id="task-1",
        agent_run_id=run_id,
        agent_name="plan-researcher",
        status=status,
        summary="worker completed",
    )


async def _write_launch_spec(tmp_path: Path) -> tuple[Path, str, Path]:
    run_store_dir = tmp_path / "subagent_runs"
    store = PerRunSubAgentRunStore(run_store_dir)
    definition = _definition()
    start_request = SubAgentStartRequest.model_validate(
        {
            "name": "plan-researcher",
            "instruction": "Research worker behavior.",
            "objective": "Inspect worker behavior",
        },
    )
    definition_match = DefinitionMatchMetadata(
        matched=True,
        definition_name="plan-researcher",
        definition_source="builtin",
        score=1.0,
    )
    record = await store.create(
        _spec(),
        definition,
        PermissionPolicy.readonly(),
        start_request=start_request,
        definition_match=definition_match,
        nickname="研究员",
    )
    launch = WorkerLaunchSpec(
        run_id=record.run_id,
        run_store_dir=str(run_store_dir),
        workspace_dir=str(tmp_path / "workspace"),
        parent_agent_config=_agent_config(tmp_path).model_dump(mode="json"),
        definition=definition,
        delegation_spec=record.spec,
        effective_policy=record.effective_policy,
        start_request=record.start_request,
        definition_match=record.definition_match,
        nickname=record.nickname,
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
            assert kwargs["run"].nickname == "研究员"
            assert kwargs["run"].start_request.name == "plan-researcher"
            assert kwargs["run"].definition_match.matched is True
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
async def test_worker_preserves_partial_runtime_result(monkeypatch, tmp_path):
    from swe.app.subagents import worker as worker_module

    class FakeRuntime:
        def __init__(self, store):
            self.store = store

        async def run(self, **kwargs):
            return _result(kwargs["run"].run_id, status="partial")

    launch_path, run_id, run_store_dir = await _write_launch_spec(tmp_path)
    monkeypatch.setattr(worker_module, "SubAgentRuntime", FakeRuntime)

    exit_code = await worker_module.run_worker(launch_path)
    record = await PerRunSubAgentRunStore(run_store_dir).get(run_id)

    assert exit_code == 0
    assert record is not None
    assert record.status == "partial"
    assert record.result is not None
    assert record.result.status == "partial"


@pytest.mark.asyncio
async def test_worker_binds_launch_identity(monkeypatch, tmp_path):
    from swe.app.subagents import worker as worker_module
    from swe.config.context import (
        get_current_effective_tenant_id,
        get_current_source_id,
        get_current_tenant_id,
        get_current_user_id,
        get_current_workspace_dir,
    )

    observed = {}

    class CapturingRuntime:
        def __init__(self, store):
            self.store = store

        async def run(self, **kwargs):
            observed["tenant_id"] = get_current_tenant_id()
            observed["effective_tenant_id"] = get_current_effective_tenant_id()
            observed["source_id"] = get_current_source_id()
            observed["user_id"] = get_current_user_id()
            observed["workspace_dir"] = get_current_workspace_dir()
            observed["request_context"] = kwargs["request_context"]
            return _result(kwargs["run"].run_id)

    launch_path, run_id, run_store_dir = await _write_launch_spec(tmp_path)
    raw = json.loads(launch_path.read_text(encoding="utf-8"))
    raw["request_context"] = {
        "session_id": "session-1",
        "tenant_id": "tenant-1",
        "source_id": "source-1",
        "scope_id": "dGVuYW50LTE.c291cmNlLTE",
        "user_id": "user-1",
    }
    launch_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(worker_module, "SubAgentRuntime", CapturingRuntime)

    exit_code = await worker_module.run_worker(launch_path)
    record = await PerRunSubAgentRunStore(run_store_dir).get(run_id)

    assert exit_code == 0
    assert record is not None
    assert observed == {
        "tenant_id": "tenant-1",
        "effective_tenant_id": "dGVuYW50LTE.c291cmNlLTE",
        "source_id": "source-1",
        "user_id": "user-1",
        "workspace_dir": tmp_path / "workspace",
        "request_context": {
            "session_id": "session-1",
            "tenant_id": "tenant-1",
            "source_id": "source-1",
            "scope_id": "dGVuYW50LTE.c291cmNlLTE",
            "user_id": "user-1",
        },
    }


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
