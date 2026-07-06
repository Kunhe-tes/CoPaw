# -*- coding: utf-8 -*-
"""Background SubAgent tool factory tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swe.agents.tools.subagent_background import (
    create_background_subagent_tools,
)
from swe.app.subagents import BackgroundSubAgentStartBlocked
from swe.app.subagents import (
    AgentResult,
    AgentRegistry,
    DelegationSpec,
    BackgroundSubAgentNotManageable,
    DefinitionMatchMetadata,
    PerRunSubAgentRunStore,
    PermissionPolicy,
    SubAgentStartRequest,
    builtin_definition_provider,
)
from swe.config.config import AgentProfileConfig, ToolsConfig


def _agent_config(tmp_path: Path) -> AgentProfileConfig:
    return AgentProfileConfig(
        id="agent-1",
        name="Agent",
        workspace_dir=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_start_subagent_returns_blocked_without_run_file(tmp_path):
    supervisor = SimpleNamespace()
    supervisor.start = _AsyncReturn(
        BackgroundSubAgentStartBlocked(
            limit=1,
            active_run_ids=["subagent-running"],
        ),
    )
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "session_id": "session-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["start_subagent"](
        name="plan-researcher",
        instruction="Act as a readonly planning researcher.",
        objective="Inspect",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "blocked"
    assert payload["reason"] == "background_subagent_concurrency_limit"
    assert not (tmp_path / "subagent_runs").exists()


@pytest.mark.asyncio
async def test_wait_subagent_returns_compact_snapshot(tmp_path):
    supervisor = SimpleNamespace()
    supervisor.wait = _AsyncReturn(
        SimpleNamespace(
            active_runs=[
                SimpleNamespace(
                    run_id="subagent-active",
                    status="running",
                    spec=SimpleNamespace(
                        name="plan-researcher",
                        objective="Inspect",
                    ),
                    result=None,
                    errors=[],
                    model_dump=lambda mode="json": {},
                ),
            ],
            terminal_runs=[],
            timed_out=True,
        ),
    )
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["wait_subagent"](timeout_ms=1)
    payload = json.loads(response.content[0]["text"])

    assert payload["timed_out"] is True
    assert payload["active_runs"][0]["run_id"] == "subagent-active"


@pytest.mark.asyncio
async def test_wait_subagent_returns_parent_facing_terminal_result(tmp_path):
    supervisor = SimpleNamespace()
    supervisor.wait = _AsyncReturn(
        SimpleNamespace(
            active_runs=[],
            terminal_runs=[
                SimpleNamespace(
                    run_id="subagent-done",
                    status="completed",
                    spec=SimpleNamespace(
                        name="plan-researcher",
                        objective="Inspect",
                    ),
                    nickname="研究员",
                    result=AgentResult(
                        task_id="task-1",
                        agent_run_id="subagent-done",
                        agent_name="plan-researcher",
                        status="completed",
                        summary="done",
                    ),
                    errors=[],
                    worker=SimpleNamespace(
                        pid=123,
                        stderr_log_path="/tmp/secret.stderr.log",
                    ),
                    definition_match=DefinitionMatchMetadata(
                        matched=True,
                        definition_name="plan-researcher",
                    ),
                ),
            ],
            timed_out=False,
        ),
    )
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["wait_subagent"](timeout_ms=1)
    payload = json.loads(response.content[0]["text"])
    terminal = payload["terminal_runs"][0]

    assert terminal == {
        "run_id": "subagent-done",
        "status": "completed",
        "agent_name": "plan-researcher",
        "nickname": "研究员",
        "objective": "Inspect",
        "result": {
            "status": "completed",
            "summary": "done",
            "findings": [],
            "relevant_files": [],
            "risks": [],
            "recommendations": [],
            "open_questions": [],
            "suggested_next_steps": [],
        },
    }


@pytest.mark.asyncio
async def test_wait_subagent_returns_error_summary_for_failed_no_result_run(
    tmp_path,
):
    supervisor = SimpleNamespace()
    supervisor.wait = _AsyncReturn(
        SimpleNamespace(
            active_runs=[],
            terminal_runs=[
                SimpleNamespace(
                    run_id="subagent-failed",
                    status="failed",
                    spec=SimpleNamespace(
                        name="plan-researcher",
                        objective="Inspect",
                    ),
                    nickname=None,
                    result=None,
                    errors=[
                        SimpleNamespace(
                            code="worker_exited_without_result",
                            message="Worker exited without producing a result.",
                        ),
                    ],
                ),
            ],
            timed_out=False,
        ),
    )
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["wait_subagent"](timeout_ms=1)
    payload = json.loads(response.content[0]["text"])
    terminal = payload["terminal_runs"][0]

    assert terminal["result"] == {
        "status": "failed",
        "summary": (
            "worker_exited_without_result: "
            "Worker exited without producing a result."
        ),
    }
    assert "errors" not in terminal


@pytest.mark.asyncio
async def test_start_subagent_serializes_real_run_record(tmp_path):
    definition = AgentRegistry([builtin_definition_provider()]).resolve(
        "plan-researcher",
    )
    record = await PerRunSubAgentRunStore(tmp_path / "runs").create(
        DelegationSpec(
            name="plan-researcher",
            objective="Inspect",
        ),
        definition,
        PermissionPolicy.readonly(),
        start_request=SubAgentStartRequest.model_validate(
            {
                "name": "plan-researcher",
                "instruction": "Act as a readonly planning researcher.",
                "objective": "Inspect",
            },
        ),
        definition_match=DefinitionMatchMetadata(
            matched=True,
            definition_name="plan-researcher",
            definition_source="builtin",
            score=1.0,
        ),
        nickname="研究员",
    )
    supervisor = SimpleNamespace()
    supervisor.start = _AsyncReturn(record)
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["start_subagent"](
        name="plan-researcher",
        instruction="Act as a readonly planning researcher.",
        objective="Inspect",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["run_id"] == record.run_id
    assert payload["accepted"] is True
    assert payload["nickname"] == "研究员"
    assert "definition_match" not in payload
    assert "worker" not in payload


@pytest.mark.asyncio
async def test_start_subagent_respects_disabled_parent_readonly_tools(
    tmp_path,
):
    captured = {}

    async def _start(**kwargs):
        captured["parent_policy"] = kwargs["parent_policy"]
        return BackgroundSubAgentStartBlocked(limit=1)

    config = _agent_config(tmp_path)
    config.tools = ToolsConfig()
    config.tools.builtin_tools["execute_shell_command"].enabled = False
    supervisor = SimpleNamespace(start=_start)
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=config,
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    await tools["start_subagent"](
        name="plan-researcher",
        instruction="Act as a readonly planning researcher.",
        objective="Inspect",
    )

    assert "execute_shell_command" not in captured["parent_policy"].tools.allow
    assert "execute_shell_command" in captured["parent_policy"].tools.deny


@pytest.mark.asyncio
async def test_start_subagent_uses_compact_request_and_falls_back_run_scoped(
    tmp_path,
):
    captured = {}

    async def _start(**kwargs):
        captured.update(kwargs)
        return BackgroundSubAgentStartBlocked(limit=1)

    supervisor = SimpleNamespace(start=_start)
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["start_subagent"](
        name="aum-customer-analyst",
        instruction="Act as a customer strategy analyst.",
        objective="Analyze 1M AUM customer maintenance.",
        background="Need structured advice.",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "blocked"
    assert captured["spec"].name == "aum-customer-analyst"
    assert captured["definition"].source == "run_scoped"
    assert captured["definition"].instruction == (
        "Act as a customer strategy analyst."
    )
    assert captured["start_request"].name == "aum-customer-analyst"
    assert captured["definition_match"].matched is False


@pytest.mark.asyncio
async def test_start_subagent_rejects_missing_instruction(tmp_path):
    tools = create_background_subagent_tools(
        supervisor=SimpleNamespace(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["start_subagent"](
        name="bad",
        instruction=" ",
        objective="Inspect",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "failed"
    assert payload["reason"] == "invalid_request"


@pytest.mark.asyncio
async def test_start_subagent_rejects_old_agent_name_field(tmp_path):
    tools = create_background_subagent_tools(
        supervisor=SimpleNamespace(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["start_subagent"](
        agent_name="legacy",
        objective="Inspect",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "failed"
    assert payload["reason"] == "invalid_request"


@pytest.mark.asyncio
async def test_start_subagent_rejects_absent_instruction(tmp_path):
    tools = create_background_subagent_tools(
        supervisor=SimpleNamespace(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["start_subagent"](
        name="bad",
        objective="Inspect",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "failed"
    assert payload["reason"] == "invalid_request"


@pytest.mark.asyncio
async def test_register_subagent_definition_returns_registration_status(
    tmp_path,
):
    tools = create_background_subagent_tools(
        supervisor=SimpleNamespace(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
        include_registration_tool=True,
    )

    response = await tools["register_subagent_definition"](
        name="aum-customer-analyst",
        instruction="Act as a customer strategy analyst.",
        description="Analyzes customer maintenance.",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload == {"status": "registered", "name": "aum-customer-analyst"}


@pytest.mark.asyncio
async def test_start_subagent_uses_matched_definition(tmp_path):
    captured = {}

    async def _start(**kwargs):
        captured.update(kwargs)
        return BackgroundSubAgentStartBlocked(limit=1)

    supervisor = SimpleNamespace(start=_start)
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_definition_store_dir": str(tmp_path / "definitions"),
        },
    )

    response = await tools["start_subagent"](
        name="risk reviewer",
        instruction="This should not override the matched definition.",
        objective="Review risk in this plan.",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "blocked"
    assert captured["definition"].name == "risk-reviewer"
    assert captured["definition"].source == "builtin"
    assert captured["definition"].instruction != (
        "This should not override the matched definition."
    )
    assert isinstance(captured["definition_match"], DefinitionMatchMetadata)
    assert captured["definition_match"].matched is True


@pytest.mark.asyncio
async def test_get_and_cancel_invalid_run_id_return_not_found(tmp_path):
    supervisor = SimpleNamespace()
    supervisor.get = _AsyncRaise(ValueError("bad run id"))
    supervisor.cancel = _AsyncRaise(ValueError("bad run id"))
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"tenant_id": "tenant-1", "agent_id": "agent-1"},
    )

    get_response = await tools["get_subagent"]("../other")
    cancel_response = await tools["cancel_subagent"]("../other")

    assert json.loads(get_response.content[0]["text"]) == {
        "status": "not_found",
        "run_id": "../other",
    }
    assert json.loads(cancel_response.content[0]["text"]) == {
        "status": "not_found",
        "run_id": "../other",
    }


@pytest.mark.asyncio
async def test_get_subagent_includes_manageable_and_stderr_tail(tmp_path):
    run_store_dir = tmp_path / "runs"
    definition = AgentRegistry([builtin_definition_provider()]).resolve(
        "plan-researcher",
    )
    store = PerRunSubAgentRunStore(run_store_dir)
    record = await store.create(
        DelegationSpec(name="plan-researcher", objective="Inspect"),
        definition,
        PermissionPolicy.readonly(),
    )
    stderr_path = run_store_dir / f"{record.run_id}.stderr.log"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text("x" * 5000, encoding="utf-8")
    await store.mark_running(
        record.run_id,
        worker_pid=123,
        stderr_log_path=str(stderr_path),
    )
    failed = await store.fail(record.run_id, "boom")
    supervisor = SimpleNamespace()
    supervisor.get = _AsyncReturn(failed)
    supervisor.is_manageable = lambda _scope, run_id: run_id == record.run_id
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_run_store_dir": str(run_store_dir),
        },
    )

    response = await tools["get_subagent"](
        record.run_id,
        include_details=True,
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["manageable"] is True
    assert payload["stderr_tail"] == "x" * 4096
    assert "stderr_log_path" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_get_subagent_defaults_to_parent_facing_projection(tmp_path):
    definition = AgentRegistry([builtin_definition_provider()]).resolve(
        "plan-researcher",
    )
    store = PerRunSubAgentRunStore(tmp_path / "runs")
    record = await store.create(
        DelegationSpec(name="plan-researcher", objective="Inspect"),
        definition,
        PermissionPolicy.readonly(),
    )
    completed = await store.finish(
        record.run_id,
        AgentResult(
            task_id="task-1",
            agent_run_id=record.run_id,
            agent_name="plan-researcher",
            status="completed",
            summary="done",
        ),
    )
    supervisor = SimpleNamespace()
    supervisor.get = _AsyncReturn(completed)
    supervisor.is_manageable = lambda _scope, _run_id: False
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_run_store_dir": str(tmp_path / "runs"),
        },
    )

    response = await tools["get_subagent"](record.run_id)
    payload = json.loads(response.content[0]["text"])

    assert payload["result"]["summary"] == "done"
    assert "definition_match" not in payload
    assert "worker" not in payload
    assert "errors" not in payload


@pytest.mark.asyncio
async def test_get_subagent_returns_error_summary_for_failed_no_result_run(
    tmp_path,
):
    definition = AgentRegistry([builtin_definition_provider()]).resolve(
        "plan-researcher",
    )
    store = PerRunSubAgentRunStore(tmp_path / "runs")
    record = await store.create(
        DelegationSpec(name="plan-researcher", objective="Inspect"),
        definition,
        PermissionPolicy.readonly(),
    )
    failed = await store.fail(record.run_id, "worker failed to start")
    supervisor = SimpleNamespace()
    supervisor.get = _AsyncReturn(failed)
    supervisor.is_manageable = lambda _scope, _run_id: False
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "_subagent_run_store_dir": str(tmp_path / "runs"),
        },
    )

    response = await tools["get_subagent"](record.run_id)
    payload = json.loads(response.content[0]["text"])

    assert payload["result"] == {
        "status": "failed",
        "summary": "runtime_error: worker failed to start",
    }
    assert "errors" not in payload


class _AsyncReturn:
    def __init__(self, value):
        self.value = value

    async def __call__(self, *args, **kwargs):
        return self.value


class _AsyncRaise:
    def __init__(self, error):
        self.error = error

    async def __call__(self, *args, **kwargs):
        raise self.error
