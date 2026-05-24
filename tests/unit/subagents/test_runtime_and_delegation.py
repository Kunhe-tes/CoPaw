# -*- coding: utf-8 -*-
"""SubAgent runtime and delegation manager tests."""

from __future__ import annotations

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
    PermissionPolicy,
    SubAgentRuntime,
    builtin_definition_provider,
)
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
