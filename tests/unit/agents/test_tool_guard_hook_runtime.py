# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio

import pytest
from agentscope.message import Msg

from swe.agents.hook_runtime.models import (
    AdditionalContext,
    CommandHookHandlerConfig,
    HookConfig,
    HookDecision,
    HookEventName,
    HookHandlerResult,
    HookMatcherGroupConfig,
    HookSessionState,
    LoadedSkillHookSource,
    MergedHookResult,
)
from swe.agents.skill_invocation_detector import SkillInvocationDetector
from swe.agents.skill_tool_registry import SkillToolRegistry
from swe.agents.tool_guard_mixin import ToolGuardMixin


class _Memory:
    def __init__(self):
        self.content = []

    async def add(self, msg, marks=None):
        self.content.append((msg, marks))


class _BaseAgent:
    async def _acting(self, tool_call):
        return {"content": tool_call["input"]}

    async def _reasoning(self, tool_choice=None):
        return Msg("Friday", "base reasoning", "assistant")


class _FakeAgent(ToolGuardMixin, _BaseAgent):
    name = "Friday"

    def __init__(self, tmp_path: Path):
        self._request_context = {
            "session_id": "session-1",
            "user_id": "user-1",
            "channel": "console",
            "agent_id": "agent-1",
        }
        self._agent_config = SimpleNamespace()
        self._workspace_dir = tmp_path
        self.memory = _Memory()
        self.printed = []
        self._tool_guard_lock = asyncio.Lock()

    def _ensure_tool_guard(self) -> None:
        self._tool_guard_engine = SimpleNamespace(enabled=False)

    async def print(self, msg, *args, **kwargs):
        self.printed.append(msg)


@pytest.mark.asyncio
async def test_no_hook_config_preserves_tool_execution(tmp_path) -> None:
    agent = _FakeAgent(tmp_path)

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "read_file",
            "input": {"path": "README.md"},
        },
    )

    assert result == {"content": {"path": "README.md"}}
    assert agent.memory.content == []


def test_tool_hooks_enabled_accepts_loaded_skill_sources(tmp_path) -> None:
    agent = _FakeAgent(tmp_path)
    agent._request_context["_hook_overlay_model"] = HookSessionState(
        loaded_skill_sources=[
            LoadedSkillHookSource(
                source_id="skill:xlsx",
                skill_name="xlsx",
                skill_root="/workspace/skills/xlsx",
                source_path="/workspace/skills/xlsx/hooks/hooks.json",
                hook_config=HookConfig(
                    enabled=True,
                    events={
                        HookEventName.PRE_TOOL_USE: [
                            HookMatcherGroupConfig(
                                id="skill:xlsx:shell",
                                hooks=[
                                    CommandHookHandlerConfig(
                                        id="skill:xlsx:hook",
                                        command="echo {}",
                                    ),
                                ],
                            ),
                        ],
                    },
                ),
            ),
        ],
    )

    assert agent._tool_hooks_enabled(HookConfig())


@pytest.mark.asyncio
async def test_pre_tool_hook_updated_input_replaces_tool_call(
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._emit_tool_hook = AsyncMock(
        side_effect=[
            MergedHookResult(updated_input={"cmd": "echo replaced"}),
            MergedHookResult(),
        ],
    )

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )

    assert result == {"content": {"cmd": "echo replaced"}}


@pytest.mark.asyncio
async def test_pre_tool_hook_denial_returns_tool_result(tmp_path) -> None:
    agent = _FakeAgent(tmp_path)
    agent._emit_tool_hook = AsyncMock(
        return_value=MergedHookResult(
            decision=HookDecision.DENY,
            reason="no shell",
        ),
    )

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )

    assert result is None
    assert "no shell" in str(agent.printed[0].content)


@pytest.mark.asyncio
async def test_pre_tool_hook_denial_does_not_request_approval(
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._emit_tool_hook = AsyncMock(
        return_value=MergedHookResult(
            decision=HookDecision.DENY,
            reason="no shell",
        ),
    )
    agent._emit_waiting_for_approval = AsyncMock(
        return_value=Msg("Friday", "approval", "assistant"),
    )

    await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )
    result = await agent._reasoning()

    assert result.content == "base reasoning"
    agent._emit_waiting_for_approval.assert_not_awaited()


@pytest.mark.asyncio
async def test_pre_tool_hook_ask_uses_existing_approval_path(tmp_path) -> None:
    agent = _FakeAgent(tmp_path)
    agent._emit_tool_hook = AsyncMock(
        return_value=MergedHookResult(
            decision=HookDecision.ASK,
            reason="review shell",
        ),
    )
    agent._acting_with_approval = AsyncMock(return_value=None)

    await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )

    agent._acting_with_approval.assert_awaited_once()
    guard_result = agent._acting_with_approval.await_args.args[2]
    assert guard_result.findings[0].guardian == "unified_hook_runtime"


@pytest.mark.asyncio
async def test_approved_pre_tool_hook_ask_replay_executes_once(
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._tool_guard_replay_approval = {
        "request_id": "approval-1",
        "approval_kind": "hook_pre_tool_use",
        "tool_call_id": "tool-1",
        "tool_name": "execute_shell_command",
        "tool_input": {"cmd": "echo original"},
        "hook_ask_handler_ids": ["hook-a"],
    }
    agent._emit_tool_hook = AsyncMock(
        return_value=MergedHookResult(
            decision=HookDecision.ASK,
            reason="review shell",
            permission_decisions=[
                {
                    "handler_id": "hook-a",
                    "decision": HookDecision.ASK,
                    "reason": "review shell",
                },
            ],
        ),
    )
    agent._acting_with_approval = AsyncMock(return_value=None)

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )

    assert result == {"content": {"cmd": "echo original"}}
    agent._acting_with_approval.assert_not_awaited()


@pytest.mark.asyncio
async def test_pre_tool_prompt_allow_does_not_bypass_tool_guard(
    monkeypatch,
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._emit_tool_hook = AsyncMock(
        return_value=MergedHookResult(
            decision=HookDecision.ALLOW,
            reason="prompt allowed",
        ),
    )
    agent._acting_with_approval = AsyncMock(return_value=None)
    agent._tool_guard_engine = SimpleNamespace(
        enabled=True,
        is_denied=lambda _tool_name: False,
        is_guarded=lambda _tool_name: False,
        guard=lambda *_args, **_kwargs: SimpleNamespace(
            findings=[object()],
        ),
    )
    agent._ensure_tool_guard = lambda: None
    monkeypatch.setattr(
        "swe.security.tool_guard.utils.log_findings",
        lambda *_args, **_kwargs: None,
    )

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )

    assert result is None
    agent._acting_with_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_approved_pre_tool_hook_ask_replay_does_not_cover_new_ask_handler(
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._tool_guard_replay_approval = {
        "request_id": "approval-1",
        "approval_kind": "hook_pre_tool_use",
        "tool_call_id": "tool-1",
        "tool_name": "execute_shell_command",
        "tool_input": {"cmd": "echo original"},
        "hook_ask_handler_ids": ["hook-a"],
    }
    agent._emit_tool_hook = AsyncMock(
        return_value=MergedHookResult(
            decision=HookDecision.ASK,
            reason="review shell",
            permission_decisions=[
                {
                    "handler_id": "hook-a",
                    "decision": HookDecision.ASK,
                    "reason": "review shell",
                },
                {
                    "handler_id": "hook-b",
                    "decision": HookDecision.ASK,
                    "reason": "new policy",
                },
            ],
        ),
    )
    agent._acting_with_approval = AsyncMock(return_value=None)

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )

    assert result is None
    agent._acting_with_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_approved_pre_tool_hook_ask_replay_does_not_bypass_deny(
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._tool_guard_replay_approval = {
        "request_id": "approval-1",
        "approval_kind": "hook_pre_tool_use",
        "tool_call_id": "tool-1",
        "tool_name": "execute_shell_command",
        "tool_input": {"cmd": "echo original"},
        "hook_ask_handler_ids": ["hook-a"],
    }
    agent._emit_tool_hook = AsyncMock(
        return_value=MergedHookResult(
            decision=HookDecision.DENY,
            reason="blocked now",
            permission_decisions=[
                {
                    "handler_id": "hook-a",
                    "decision": HookDecision.ASK,
                    "reason": "review shell",
                },
            ],
        ),
    )
    agent._acting_with_approval = AsyncMock(return_value=None)

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )

    assert result is None
    assert "blocked now" in str(agent.printed[0].content)
    agent._acting_with_approval.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_pre_tool_hook_ask_replay_reasks_when_input_changes(
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._tool_guard_replay_approval = {
        "request_id": "approval-1",
        "approval_kind": "hook_pre_tool_use",
        "tool_call_id": "tool-1",
        "tool_name": "execute_shell_command",
        "tool_input": {"cmd": "echo original"},
        "hook_ask_handler_ids": ["hook-a"],
    }
    agent._emit_tool_hook = AsyncMock(
        return_value=MergedHookResult(
            decision=HookDecision.ASK,
            reason="review shell",
            updated_input={"cmd": "echo changed"},
            permission_decisions=[
                {
                    "handler_id": "hook-a",
                    "decision": HookDecision.ASK,
                    "reason": "review shell",
                },
            ],
        ),
    )
    agent._acting_with_approval = AsyncMock(return_value=None)

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"cmd": "echo original"},
        },
    )

    assert result is None
    agent._acting_with_approval.assert_awaited_once()
    assert agent._acting_with_approval.await_args.args[0]["input"] == {
        "cmd": "echo changed",
    }


@pytest.mark.asyncio
async def test_post_tool_hook_additional_context_is_added_to_memory(
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._emit_tool_hook = AsyncMock(
        side_effect=[
            MergedHookResult(),
            MergedHookResult(
                additional_context=[
                    AdditionalContext(
                        handler_id="post",
                        context="remember me",
                    ),
                ],
            ),
        ],
    )

    await agent._acting(
        {
            "id": "tool-1",
            "name": "read_file",
            "input": {"path": "README.md"},
        },
    )

    assert "remember me" in agent.memory.content[-1][0].content
    assert agent.memory.content[-1][0].role == "developer"


@pytest.mark.asyncio
async def test_tool_failure_hook_block_reason_is_added_to_memory(
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    agent._run_tool_call_with_hard_timeout = AsyncMock(
        side_effect=RuntimeError("tool failed"),
    )
    agent._emit_tool_hook = AsyncMock(
        side_effect=[
            MergedHookResult(),
            MergedHookResult(
                decision=HookDecision.BLOCK,
                reason="failure context",
            ),
        ],
    )

    with pytest.raises(RuntimeError):
        await agent._acting(
            {
                "id": "tool-1",
                "name": "read_file",
                "input": {"path": "README.md"},
            },
        )

    assert "failure context" in agent.memory.content[-1][0].content
    assert agent.memory.content[-1][0].role == "developer"


@pytest.mark.asyncio
async def test_tool_hook_once_state_is_written_back_to_request_context(
    monkeypatch,
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    tenant_hooks = HookConfig(
        enabled=True,
        events={
            HookEventName.PRE_TOOL_USE: [
                HookMatcherGroupConfig(
                    hooks=[
                        CommandHookHandlerConfig(
                            id="once",
                            command="echo {}",
                            once=True,
                        ),
                    ],
                ),
            ],
        },
    )
    calls = []

    async def fake_execute_handler(handler, context, *, workspace_dir):
        calls.append((handler.id, context.hook_event_name, workspace_dir))
        return HookHandlerResult(handler_id=handler.id, order=0)

    monkeypatch.setattr(
        "swe.agents.tool_guard_mixin.ToolGuardMixin._load_tenant_hook_config",
        lambda self: tenant_hooks,
    )
    monkeypatch.setattr(
        "swe.agents.hook_runtime.runtime.execute_handler",
        fake_execute_handler,
    )

    await agent._emit_tool_hook(
        HookEventName.PRE_TOOL_USE,
        tool_name="execute_shell_command",
        tool_input={"cmd": "echo one"},
        tool_use_id="tool-1",
    )
    await agent._emit_tool_hook(
        HookEventName.PRE_TOOL_USE,
        tool_name="execute_shell_command",
        tool_input={"cmd": "echo two"},
        tool_use_id="tool-2",
    )

    assert [call[0] for call in calls] == ["once"]
    hook_overlay = agent._request_context["hook_overlay"]
    assert isinstance(hook_overlay, dict)
    once_executed = hook_overlay["once_executed"]
    assert once_executed == {
        "default:user-1:session-1:PreToolUse:once": True,
    }


@pytest.mark.asyncio
async def test_skill_activation_loads_hooks_for_later_tool_event(
    monkeypatch,
    tmp_path,
) -> None:
    agent = _FakeAgent(tmp_path)
    registry = SkillToolRegistry()
    registry.register_skill_tools("xlsx", ["read_file"])
    loaded_state = HookSessionState()

    async def load_skill_hooks(skill_name: str) -> None:
        nonlocal loaded_state
        loaded_state = HookSessionState(
            loaded_skill_sources=[
                LoadedSkillHookSource(
                    source_id=f"skill:{skill_name}",
                    skill_name=skill_name,
                    skill_root=str(tmp_path / "skills" / skill_name),
                    source_path=str(
                        tmp_path / "skills" / skill_name / "hooks/hooks.json",
                    ),
                    hook_config=HookConfig(
                        enabled=True,
                        events={
                            HookEventName.POST_TOOL_USE: [
                                HookMatcherGroupConfig(
                                    id=f"skill:{skill_name}:post",
                                    hooks=[
                                        CommandHookHandlerConfig(
                                            id=f"skill:{skill_name}:post-hook",
                                            command="echo {}",
                                        ),
                                    ],
                                ),
                            ],
                        },
                    ),
                ),
            ],
        )
        agent._request_context["_hook_overlay_model"] = loaded_state
        agent._request_context["hook_overlay"] = loaded_state.model_dump(
            mode="json",
            by_alias=True,
        )

    detector = SkillInvocationDetector(
        registry=registry,
        skill_hook_loader=load_skill_hooks,
    )
    detector.set_enabled_skills(["xlsx"])
    agent._request_context["_skill_invocation_detector"] = detector
    agent._request_context["_hook_overlay_model"] = loaded_state
    calls = []

    async def fake_execute_handler(handler, context, *, workspace_dir):
        calls.append((handler.id, context.hook_event_name))
        return HookHandlerResult(handler_id=handler.id, order=0)

    monkeypatch.setattr(
        "swe.agents.tool_guard_mixin.ToolGuardMixin._load_tenant_hook_config",
        lambda self: HookConfig(),
    )
    monkeypatch.setattr(
        "swe.agents.hook_runtime.runtime.execute_handler",
        fake_execute_handler,
    )

    await agent._acting(
        {
            "id": "tool-1",
            "name": "read_file",
            "input": {"path": "data.xlsx"},
        },
    )

    assert calls == [
        ("skill:xlsx:post-hook", HookEventName.POST_TOOL_USE),
    ]
