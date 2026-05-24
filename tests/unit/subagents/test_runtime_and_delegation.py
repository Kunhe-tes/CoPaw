# -*- coding: utf-8 -*-
"""SubAgent runtime and delegation manager tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import Msg

from swe.app.subagents import (
    AgentRegistry,
    AgentResult,
    DelegationManager,
    DelegationSpec,
    InMemorySubAgentRunStore,
    LocalJsonSubAgentRunStore,
    PermissionPolicy,
    SubAgentRuntime,
    builtin_definition_provider,
)
from swe.app.subagents.models import BudgetConfig
from swe.agents.tools.delegate_to_subagent import (
    create_delegate_to_subagent_tool,
)
from swe.config.config import AgentProfileConfig, ToolsConfig


class _FakeSWEAgent:
    instances: list["_FakeSWEAgent"] = []
    replies: list[Msg | Exception] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.messages: list[Msg] = []
        _FakeSWEAgent.instances.append(self)

    async def reply(self, msg=None, structured_model=None):
        self.messages.append(msg)
        reply = _FakeSWEAgent.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _agent_config(tmp_path: Path) -> AgentProfileConfig:
    return AgentProfileConfig(
        id="default",
        name="Default",
        workspace_dir=str(tmp_path),
    )


def _spec() -> DelegationSpec:
    return DelegationSpec(
        task_id="task-1",
        parent_thread_id="session-1",
        agent_name="plan-researcher",
        objective="Find relevant files",
        background="User asked for a plan",
    )


@pytest.mark.asyncio
async def test_runtime_creates_fresh_agent_with_subagent_safe_options(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runtime creates a fresh SWEAgent and sends only the DelegationSpec."""
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg(
            "Friday",
            json.dumps(
                {
                    "task_id": "task-1",
                    "agent_run_id": "ignored",
                    "agent_name": "plan-researcher",
                    "status": "completed",
                    "summary": "found files",
                },
            ),
            "assistant",
        ),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    registry = AgentRegistry([builtin_definition_provider()])
    definition = registry.resolve("plan-researcher")
    store = InMemorySubAgentRunStore()
    runtime = SubAgentRuntime(store=store)
    record = await store.create(
        _spec(),
        definition,
        PermissionPolicy.readonly(),
    )

    result = await runtime.run(
        run=record,
        definition=definition,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
        request_context={
            "session_id": "parent-session",
            "_skill_invocation_detector": object(),
            "_hook_overlay_model": object(),
            "hook_overlay": {"loaded_skill_sources": [{"source_id": "x"}]},
        },
    )

    assert result.status == "completed"
    assert result.agent_run_id == record.run_id
    created = _FakeSWEAgent.instances[0]
    assert created.kwargs["enable_memory_manager"] is False
    assert created.kwargs["mcp_clients"] == []
    assert created.kwargs["workspace_dir"] == tmp_path
    assert created.kwargs["enable_workspace_skills"] is False
    assert "system_prompt_override" in created.kwargs
    assert created.kwargs["request_context"]["agent_role"] == "subagent"
    assert (
        created.kwargs["request_context"]["subagent_run_id"] == record.run_id
    )
    assert (
        "_skill_invocation_detector" not in created.kwargs["request_context"]
    )
    assert "_hook_overlay_model" not in created.kwargs["request_context"]
    assert "hook_overlay" not in created.kwargs["request_context"]
    delegated_message = created.messages[0]
    assert delegated_message.get_text_content().count("task-1") >= 1
    assert "parent scratchpad" not in delegated_message.get_text_content()


@pytest.mark.asyncio
async def test_runtime_uses_effective_policy_for_visible_tools(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Visible SubAgent tools are narrowed by the effective policy."""
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg(
            "Friday",
            json.dumps(
                {
                    "task_id": "task-1",
                    "agent_run_id": "ignored",
                    "agent_name": "plan-researcher",
                    "status": "completed",
                    "summary": "found files",
                },
            ),
            "assistant",
        ),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    registry = AgentRegistry([builtin_definition_provider()])
    definition = registry.resolve("plan-researcher")
    store = InMemorySubAgentRunStore()
    policy = PermissionPolicy.readonly(
        allow_tools=["read_file"],
        deny_tools=["execute_shell_command"],
    )
    record = await store.create(_spec(), definition, policy)

    await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=policy,
    )

    tools = _FakeSWEAgent.instances[0].kwargs["agent_config"].tools
    assert tools.builtin_tools["read_file"].enabled is True
    assert tools.builtin_tools["execute_shell_command"].enabled is False


@pytest.mark.asyncio
async def test_runtime_applies_non_timeout_budgets_to_agent_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Turns, token cap, and tool-call budgets affect the worker run."""
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg(
            "Friday",
            json.dumps(
                {
                    "task_id": "task-1",
                    "agent_run_id": "ignored",
                    "agent_name": "plan-researcher",
                    "status": "completed",
                    "summary": "found files",
                },
            ),
            "assistant",
        ),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    registry = AgentRegistry([builtin_definition_provider()])
    definition = registry.resolve("plan-researcher").model_copy(
        update={
            "budget": BudgetConfig(
                max_turns=4,
                max_tool_calls=7,
                max_tokens=9000,
                timeout_ms=1000,
            ),
        },
    )
    spec = _spec().model_copy(
        update={
            "budget": BudgetConfig(
                max_turns=2,
                max_tool_calls=3,
                max_tokens=1000,
                timeout_ms=1000,
            ),
        },
    )
    store = InMemorySubAgentRunStore()
    record = await store.create(spec, definition, PermissionPolicy.readonly())

    await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=spec,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
    )

    created = _FakeSWEAgent.instances[0]
    assert created.kwargs["agent_config"].running.max_iters == 2
    assert created.kwargs["agent_config"].running.max_input_length == 1000
    assert created.kwargs["request_context"]["subagent_budget"] == {
        "max_turns": 2,
        "max_tool_calls": 3,
        "max_tokens": 1000,
        "timeout_ms": 1000,
    }


@pytest.mark.asyncio
async def test_runtime_repair_attempt_uses_remaining_timeout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The JSON repair attempt cannot outlive the run timeout budget."""
    from swe.app.subagents import runtime as runtime_module

    class SlowRepairAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.messages: list[Msg] = []

        async def reply(self, msg=None, structured_model=None):
            self.messages.append(msg)
            if len(self.messages) == 1:
                return Msg("Friday", "not json", "assistant")
            await asyncio.sleep(0.2)
            return Msg("Friday", "{}", "assistant")

    monkeypatch.setattr(runtime_module, "SWEAgent", SlowRepairAgent)
    registry = AgentRegistry([builtin_definition_provider()])
    definition = registry.resolve("plan-researcher").model_copy(
        update={"budget": BudgetConfig(timeout_ms=50)},
    )
    store = InMemorySubAgentRunStore()
    record = await store.create(
        _spec(),
        definition,
        PermissionPolicy.readonly(),
    )

    result = await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
    )

    assert result.status == "failed"
    assert result.errors[0].code == "timeout"


@pytest.mark.asyncio
async def test_runtime_invalid_output_uses_one_repair_attempt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Invalid output is repaired once before falling back."""
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg("Friday", "not json", "assistant"),
        Msg(
            "Friday",
            json.dumps(
                {
                    "task_id": "task-1",
                    "agent_run_id": "ignored",
                    "agent_name": "plan-researcher",
                    "status": "partial",
                    "summary": "repaired",
                },
            ),
            "assistant",
        ),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    registry = AgentRegistry([builtin_definition_provider()])
    definition = registry.resolve("plan-researcher")
    store = InMemorySubAgentRunStore()
    record = await store.create(
        _spec(),
        definition,
        PermissionPolicy.readonly(),
    )

    result = await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
    )

    assert result.status == "partial"
    assert result.summary == "repaired"
    assert len(_FakeSWEAgent.instances[0].messages) == 2


@pytest.mark.asyncio
async def test_runtime_extracts_markdown_fenced_agent_result_json(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Markdown fenced JSON is extracted and validated without repair."""
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg(
            "Friday",
            """Here is the result:

```json
{
  "task_id": "task-1",
  "agent_run_id": "ignored",
  "agent_name": "plan-researcher",
  "status": "completed",
  "summary": "from fenced json"
}
```""",
            "assistant",
        ),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    registry = AgentRegistry([builtin_definition_provider()])
    definition = registry.resolve("plan-researcher")
    store = InMemorySubAgentRunStore()
    record = await store.create(
        _spec(),
        definition,
        PermissionPolicy.readonly(),
    )

    result = await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
    )

    assert result.status == "completed"
    assert result.summary == "from fenced json"
    assert len(_FakeSWEAgent.instances[0].messages) == 1


@pytest.mark.asyncio
async def test_runtime_records_failure_as_structured_result(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unrecoverable runtime errors are persisted and returned as failures."""
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [RuntimeError("model failed")]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    registry = AgentRegistry([builtin_definition_provider()])
    definition = registry.resolve("plan-researcher")
    store = InMemorySubAgentRunStore()
    record = await store.create(
        _spec(),
        definition,
        PermissionPolicy.readonly(),
    )

    result = await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
    )

    assert result.status == "failed"
    assert result.errors
    saved = await store.get(record.run_id)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.result == result


@pytest.mark.asyncio
async def test_runtime_overrides_untrusted_model_metrics(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runtime-owned metrics are not taken from model output."""
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg(
            "Friday",
            json.dumps(
                {
                    "task_id": "task-1",
                    "agent_run_id": "ignored",
                    "agent_name": "plan-researcher",
                    "status": "completed",
                    "summary": "done",
                    "metrics": {
                        "turns_used": 99,
                        "tool_calls_used": 88,
                        "elapsed_ms": 1,
                    },
                },
            ),
            "assistant",
        ),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    registry = AgentRegistry([builtin_definition_provider()])
    definition = registry.resolve("plan-researcher")
    store = InMemorySubAgentRunStore()
    record = await store.create(
        _spec(),
        definition,
        PermissionPolicy.readonly(),
    )

    result = await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
    )

    assert result.metrics.turns_used == 1
    assert result.metrics.tool_calls_used == 0
    assert result.metrics.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_delegation_manager_resolves_records_and_invokes_runtime(
    tmp_path: Path,
) -> None:
    """Delegation manager wires registry, policy, run store, and runtime."""
    registry = AgentRegistry([builtin_definition_provider()])
    store = InMemorySubAgentRunStore()
    runtime = SimpleNamespace()
    runtime.run = AsyncMock(
        return_value=AgentResult(
            task_id="task-1",
            agent_run_id="runtime-run",
            agent_name="plan-researcher",
            status="completed",
            summary="ok",
        ),
    )
    manager = DelegationManager(
        registry=registry,
        store=store,
        runtime=runtime,
    )

    result = await manager.delegate(
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        parent_policy=PermissionPolicy.readonly(),
        request_context={"agent_role": "main"},
    )

    assert result.status == "completed"
    saved = list(store.records.values())[0]
    assert saved.definition_name == "plan-researcher"
    assert saved.definition_source == "builtin"
    runtime.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_delegation_manager_defaults_to_workspace_local_run_store(
    tmp_path: Path,
) -> None:
    """Default delegation records survive in workspace-local app state."""
    registry = AgentRegistry([builtin_definition_provider()])
    runtime = SimpleNamespace()
    runtime.run = AsyncMock(
        return_value=AgentResult(
            task_id="task-1",
            agent_run_id="runtime-run",
            agent_name="plan-researcher",
            status="completed",
            summary="ok",
        ),
    )
    manager = DelegationManager(registry=registry, runtime=runtime)

    await manager.delegate(
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        parent_policy=PermissionPolicy.readonly(),
        request_context={"agent_role": "main"},
    )

    local_store = LocalJsonSubAgentRunStore(tmp_path)
    records = list(local_store.records.values())
    assert len(records) == 1
    assert records[0].definition_name == "plan-researcher"
    assert records[0].status == "queued"


@pytest.mark.asyncio
async def test_delegation_manager_rejects_unknown_and_nested_subagent(
    tmp_path: Path,
) -> None:
    """Unknown names and SubAgent callers fail with structured results."""
    manager = DelegationManager(
        registry=AgentRegistry([builtin_definition_provider()]),
        store=InMemorySubAgentRunStore(),
    )

    unknown = await manager.delegate(
        spec=_spec().model_copy(update={"agent_name": "missing"}),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
    )
    nested = await manager.delegate(
        spec=_spec(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"agent_role": "subagent"},
    )

    assert unknown.status == "failed"
    assert "Unknown SubAgent" in unknown.summary
    assert nested.status == "blocked"
    assert "Nested delegation" in nested.summary


@pytest.mark.asyncio
async def test_delegate_tool_returns_compact_agent_result_without_transcript(
    tmp_path: Path,
) -> None:
    """Main-agent tool returns AgentResult JSON, not raw SubAgent chatter."""
    manager = SimpleNamespace()
    manager.delegate = AsyncMock(
        return_value=AgentResult(
            task_id="task-1",
            agent_run_id="run-1",
            agent_name="plan-researcher",
            status="completed",
            summary="compact summary",
        ),
    )
    tool = create_delegate_to_subagent_tool(
        manager=manager,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"session_id": "parent-session", "agent_role": "main"},
    )

    response = await tool("plan-researcher", "Inspect code", "raw transcript")

    payload = json.loads(response.content[0]["text"])
    assert payload["status"] == "completed"
    assert payload["summary"] == "compact summary"
    assert "raw transcript" not in response.content[0]["text"]
    manager.delegate.assert_awaited_once()


@pytest.mark.asyncio
async def test_delegate_tool_parent_policy_respects_disabled_parent_tools(
    tmp_path: Path,
) -> None:
    """SubAgent effective permissions cannot exceed parent tool config."""
    manager = SimpleNamespace()
    manager.delegate = AsyncMock(
        return_value=AgentResult(
            task_id="task-1",
            agent_run_id="run-1",
            agent_name="plan-researcher",
            status="completed",
            summary="compact summary",
        ),
    )
    parent_config = _agent_config(tmp_path)
    parent_config.tools = ToolsConfig()
    parent_config.tools.builtin_tools["execute_shell_command"].enabled = False
    tool = create_delegate_to_subagent_tool(
        manager=manager,
        parent_agent_config=parent_config,
        workspace_dir=tmp_path,
        request_context={"session_id": "parent-session", "agent_role": "main"},
    )

    await tool("plan-researcher", "Inspect code")

    parent_policy = manager.delegate.await_args.kwargs["parent_policy"]
    assert "execute_shell_command" not in parent_policy.tools.allow
    assert "execute_shell_command" in parent_policy.tools.deny
