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
    SubAgentDefinition,
    SubAgentResponse,
    SubAgentRuntime,
    builtin_definition_provider,
)
from swe.app.subagents.models import BudgetConfig
from swe.config.config import AgentProfileConfig


class _FakeSWEAgent:
    instances: list["_FakeSWEAgent"] = []
    replies: list[Msg | Exception] = []
    final_payloads: list[dict | Exception | None] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.messages: list[Msg] = []
        self.formatter = SimpleNamespace(format=self._format)
        self.model = self._model
        _FakeSWEAgent.instances.append(self)

    async def _format(self, messages):
        return messages

    async def run_research_phase(self, msg=None):
        self.messages.append(msg)
        reply = _FakeSWEAgent.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            status="completed",
            reply=reply,
            turns_used=1,
            messages=(msg, reply),
        )

    async def _model(self, prompt, **kwargs):
        self.finalization_prompt = prompt
        self.finalization_kwargs = kwargs
        payload = (
            _FakeSWEAgent.final_payloads.pop(0)
            if _FakeSWEAgent.final_payloads
            else {"summary": "finalized"}
        )
        if isinstance(payload, Exception):
            raise RuntimeError(str(payload))
        metadata = None if payload is None else {"structured_output": payload}
        return SimpleNamespace(metadata=metadata)


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
        name="plan-researcher",
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
    _FakeSWEAgent.replies = [Msg("Friday", "found files", "assistant")]
    _FakeSWEAgent.final_payloads = [{"summary": "found files"}]
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
    assert created.finalization_kwargs == {
        "structured_model": SubAgentResponse,
    }


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
    """Turns and tool-call budgets affect the worker run."""
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
                timeout_ms=1000,
            ),
        },
    )
    spec = _spec().model_copy(
        update={
            "budget": BudgetConfig(
                max_turns=2,
                max_tool_calls=3,
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
    assert created.kwargs["request_context"]["subagent_budget"] == {
        "max_turns": 2,
        "max_tool_calls": 3,
        "timeout_ms": 1000,
    }


@pytest.mark.asyncio
async def test_runtime_uses_definition_instruction_and_no_max_tokens(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg(
            "Friday",
            json.dumps(
                {
                    "task_id": "task-1",
                    "agent_run_id": "ignored",
                    "agent_name": "custom-worker",
                    "status": "completed",
                    "summary": "done",
                },
            ),
            "assistant",
        ),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    definition = SubAgentDefinition.model_validate(
        {
            "name": "custom-worker",
            "nickname": "研究员",
            "description": "Custom test worker.",
            "instruction": "Use the canonical instruction field only.",
            "output_contract": "Return AgentResult JSON.",
            "owner_scope": "tenant/agent",
            "source": "run_scoped",
            "tools": {"allow": ["read_file"]},
            "budget": {
                "max_turns": 3,
                "max_tool_calls": 4,
                "timeout_ms": 5000,
            },
        },
    )
    spec = DelegationSpec(
        task_id="task-1",
        parent_thread_id="session-1",
        name="custom-worker",
        objective="Inspect runtime prompt",
    )
    store = InMemorySubAgentRunStore()
    record = await store.create(
        spec,
        definition,
        PermissionPolicy.readonly(),
    )

    result = await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=spec,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
    )

    created = _FakeSWEAgent.instances[0]
    prompt = created.kwargs["system_prompt_override"]
    config_payload = created.kwargs["agent_config"].model_dump(mode="json")
    assert result.status == "completed"
    assert "Use the canonical instruction field only." in prompt
    assert "Return AgentResult JSON." not in prompt
    assert "natural-language research synthesis" in prompt
    assert "Return AgentResult JSON." in (
        created.finalization_prompt[0].get_text_content()
    )
    assert "prompt.system" not in prompt
    assert "max_tokens" not in json.dumps(config_payload)


@pytest.mark.asyncio
async def test_runtime_research_timeout_skips_finalization(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Research timeout fails without starting structured finalization."""
    from swe.app.subagents import runtime as runtime_module

    class SlowResearchAgent:
        instances: list["SlowResearchAgent"] = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.model_calls = 0
            SlowResearchAgent.instances.append(self)

        async def run_research_phase(self, msg=None):
            await asyncio.sleep(0.2)

        async def model(self, *args, **kwargs):
            self.model_calls += 1

    monkeypatch.setattr(runtime_module, "SWEAgent", SlowResearchAgent)
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
    assert SlowResearchAgent.instances[0].model_calls == 0


@pytest.mark.asyncio
async def test_runtime_missing_finalization_metadata_returns_partial_once(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Missing finalization metadata returns partial without retrying."""
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg("Friday", "research synthesis", "assistant"),
    ]
    _FakeSWEAgent.final_payloads = [None]
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
    assert result.summary == "research synthesis"
    assert result.errors[0].code == "structured_finalization_failed"
    assert result.metrics.turns_used == 2
    assert len(_FakeSWEAgent.instances[0].messages) == 1


@pytest.mark.asyncio
async def test_runtime_finalization_exception_returns_partial_once(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg("Friday", "research synthesis", "assistant"),
    ]
    _FakeSWEAgent.final_payloads = [RuntimeError("response_format rejected")]
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
    assert result.summary == "research synthesis"
    assert result.errors[0].code == "structured_finalization_failed"
    assert result.metrics.turns_used == 2
    assert len(_FakeSWEAgent.instances[0].messages) == 1


@pytest.mark.asyncio
async def test_runtime_invalid_finalization_payload_returns_partial_once(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg("Friday", "research synthesis", "assistant"),
    ]
    _FakeSWEAgent.final_payloads = [{"findings": []}]
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
    assert result.summary == "research synthesis"
    assert result.errors[0].code == "structured_finalization_failed"
    assert result.metrics.turns_used == 2


@pytest.mark.asyncio
async def test_runtime_finalization_timeout_returns_partial(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.subagents import runtime as runtime_module

    class SlowFinalizationAgent(_FakeSWEAgent):
        async def _model(self, prompt, **kwargs):
            await asyncio.sleep(0.2)
            return SimpleNamespace(
                metadata={"structured_output": {"summary": "x"}},
            )

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg("Friday", "research synthesis", "assistant"),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", SlowFinalizationAgent)
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

    assert result.status == "partial"
    assert result.errors[0].code == "structured_finalization_failed"
    assert result.metrics.turns_used == 2


@pytest.mark.asyncio
async def test_runtime_turn_limit_finalizes_from_bounded_research_record(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.subagents import runtime as runtime_module

    class TurnLimitAgent(_FakeSWEAgent):
        async def run_research_phase(self, msg=None):
            self.messages.append(msg)
            return SimpleNamespace(
                status="turn_limit_reached",
                reply=Msg(
                    "Friday",
                    [
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "read_file",
                            "input": {"path": "README.md"},
                        },
                    ],
                    "assistant",
                ),
                turns_used=2,
                messages=(
                    msg,
                    Msg(
                        "system",
                        [{"type": "tool_result", "output": "tool evidence"}],
                        "system",
                    ),
                ),
            )

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.final_payloads = [{"summary": "bounded evidence"}]
    monkeypatch.setattr(runtime_module, "SWEAgent", TurnLimitAgent)
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

    created = _FakeSWEAgent.instances[0]
    context = json.loads(created.finalization_prompt[1].get_text_content())
    assert result.status == "partial"
    assert result.summary == "bounded evidence"
    assert result.metrics.turns_used == 3
    assert result.errors[0].code == "research_turn_limit_reached"
    assert "tool evidence" in context["research_record"]


@pytest.mark.asyncio
async def test_runtime_uses_structured_metadata_not_research_text_json(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Free-form research JSON is not parsed as a terminal result."""
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
    _FakeSWEAgent.final_payloads = [
        {"summary": "from structured metadata"},
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
    assert result.summary == "from structured metadata"
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
    _FakeSWEAgent.replies = [Msg("Friday", "done", "assistant")]
    _FakeSWEAgent.final_payloads = [{"summary": "done"}]
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

    assert result.metrics.turns_used == 2
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
async def test_delegation_manager_defaults_to_app_state_run_store(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Default delegation records stay out of delegated checkout roots."""
    repo_checkout = tmp_path / "repo-checkout"
    repo_checkout.mkdir()
    app_state_root = tmp_path / "app-state"
    monkeypatch.setattr("swe.config.utils.WORKING_DIR", app_state_root)
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
        parent_agent_config=_agent_config(repo_checkout),
        workspace_dir=repo_checkout,
        parent_policy=PermissionPolicy.readonly(),
        request_context={"agent_role": "main"},
    )

    assert not (repo_checkout / "subagent_runs.json").exists()
    local_store = LocalJsonSubAgentRunStore(
        app_state_root / "default" / "workspaces" / "default",
    )
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
        spec=_spec().model_copy(update={"name": "missing"}),
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
