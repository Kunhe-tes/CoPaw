# -*- coding: utf-8 -*-
"""Integration seams between SubAgents, SWEAgent, and ToolGuardMixin."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from swe.agents import react_agent as react_agent_module
from swe.agents.hook_runtime.models import MergedHookResult
from swe.agents.react_agent import SWEAgent
from swe.agents.tool_guard_mixin import ToolGuardMixin
from swe.app.subagents import PermissionPolicy
from swe.config.config import AgentProfileConfig


class _Memory:
    def __init__(self):
        self.content = []

    async def add(self, msg, marks=None):
        self.content.append((msg, marks or []))


class _BaseAgent:
    async def _acting(self, tool_call):
        return {"content": tool_call["input"]}


class _FakeGuardAgent(ToolGuardMixin, _BaseAgent):
    name = "Friday"

    def __init__(
        self,
        tmp_path: Path,
        policy: PermissionPolicy,
        *,
        subagent_budget: dict | None = None,
    ):
        self._request_context = {
            "session_id": "session-1",
            "agent_role": "subagent",
            "subagent_policy": policy.model_dump(mode="json"),
        }
        if subagent_budget is not None:
            self._request_context["subagent_budget"] = subagent_budget
        self._agent_config = SimpleNamespace()
        self._workspace_dir = tmp_path
        self.memory = _Memory()
        self.printed = []
        self._tool_guard_lock = asyncio.Lock()
        self._emit_tool_hook_called = False
        self._acting_with_approval_called = False

    def _ensure_tool_guard(self) -> None:
        self._tool_guard_engine = SimpleNamespace(enabled=False)

    async def _emit_tool_hook(self, *args, **kwargs):
        self._emit_tool_hook_called = True
        return MergedHookResult()

    async def _acting_with_approval(self, *args, **kwargs):
        self._acting_with_approval_called = True
        raise AssertionError("SubAgent hard policy must not request approval")

    async def print(self, msg, *args, **kwargs):
        self.printed.append(msg)


def _bare_agent(tmp_path: Path, *, request_context=None) -> SWEAgent:
    agent = object.__new__(SWEAgent)
    agent._request_context = dict(request_context or {})
    agent._workspace_dir = tmp_path
    agent._env_context = None
    agent._agent_config = AgentProfileConfig(
        id="default",
        name="Default",
        workspace_dir=str(tmp_path),
    )
    agent._namesake_strategy = "skip"
    agent._effective_skills = []
    return agent


def test_system_prompt_override_bypasses_normal_main_prompt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """SubAgent prompt override is not appended to the normal main prompt."""
    monkeypatch.setattr(
        react_agent_module,
        "build_system_prompt_from_working_dir",
        lambda **_: "main prompt",
    )
    agent = _bare_agent(
        tmp_path,
        request_context={"agent_role": "subagent"},
    )
    agent._system_prompt_override = "subagent prompt"

    prompt = SWEAgent._build_sys_prompt(agent)

    assert prompt == "subagent prompt"


def test_disable_workspace_skills_leaves_no_effective_skills(
    tmp_path: Path,
) -> None:
    """SubAgent construction can skip workspace skill registration."""
    agent = _bare_agent(tmp_path)
    agent._enable_workspace_skills = False
    toolkit = SimpleNamespace()

    SWEAgent._register_skills(agent, toolkit)

    assert agent.get_effective_skills() == []


def test_subagent_toolkit_filters_builtins_and_excludes_delegate(
    tmp_path: Path,
) -> None:
    """Readonly SubAgent toolkit contains only effective allowed built-ins."""
    config = AgentProfileConfig(
        id="default",
        name="Default",
        workspace_dir=str(tmp_path),
    )
    agent = _bare_agent(
        tmp_path,
        request_context={
            "agent_role": "subagent",
            "enable_subagents": True,
            "subagent_policy": PermissionPolicy.readonly().model_dump(
                mode="json",
            ),
        },
    )
    agent._agent_config = config

    toolkit = SWEAgent._create_toolkit(agent)

    assert set(toolkit.tools) == {
        "execute_shell_command",
        "read_file",
        "grep_search",
        "glob_search",
        "get_current_time",
    }
    assert "delegate_to_subagent" not in toolkit.tools


def test_main_agent_registers_delegation_tool_only_when_enabled(
    tmp_path: Path,
) -> None:
    """Normal chat defaults stay unchanged unless delegation is enabled."""
    disabled = _bare_agent(tmp_path, request_context={"agent_role": "main"})
    enabled = _bare_agent(
        tmp_path,
        request_context={"agent_role": "main", "enable_subagents": True},
    )

    assert (
        "delegate_to_subagent" not in SWEAgent._create_toolkit(disabled).tools
    )
    assert "delegate_to_subagent" in SWEAgent._create_toolkit(enabled).tools


@pytest.mark.asyncio
async def test_subagent_hard_policy_denies_before_hooks_and_approvals(
    tmp_path: Path,
) -> None:
    """Forbidden SubAgent calls are blocked before hook or approval flow."""
    agent = _FakeGuardAgent(tmp_path, PermissionPolicy.readonly())

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "write_file",
            "input": {"path": "x", "content": "no"},
        },
    )

    assert result is None
    assert agent._emit_tool_hook_called is False
    assert agent._acting_with_approval_called is False
    assert "blocked by SubAgent policy" in str(agent.printed[0].content)


@pytest.mark.asyncio
async def test_subagent_hard_policy_allows_readonly_shell(
    tmp_path: Path,
) -> None:
    """Allowed readonly commands continue to normal tool execution."""
    agent = _FakeGuardAgent(tmp_path, PermissionPolicy.readonly())

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"command": "git status --short"},
        },
    )

    assert result == {"content": {"command": "git status --short"}}


@pytest.mark.asyncio
async def test_subagent_hard_policy_rechecks_hook_updated_input(
    tmp_path: Path,
) -> None:
    """Hook-updated input cannot widen readonly SubAgent permissions."""
    agent = _FakeGuardAgent(tmp_path, PermissionPolicy.readonly())

    async def _rewrite_to_mutating_shell(*args, **kwargs):
        agent._emit_tool_hook_called = True
        return MergedHookResult(
            updated_input={
                "command": "git status --short > /tmp/subagent-mutates",
            },
        )

    agent._emit_tool_hook = _rewrite_to_mutating_shell

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"command": "git status --short"},
        },
    )

    assert result is None
    assert agent._emit_tool_hook_called is True
    assert "blocked by SubAgent policy" in str(agent.printed[0].content)


@pytest.mark.asyncio
async def test_subagent_tool_call_budget_denies_extra_calls(
    tmp_path: Path,
) -> None:
    """Readonly SubAgents stop tool execution after max_tool_calls."""
    agent = _FakeGuardAgent(
        tmp_path,
        PermissionPolicy.readonly(),
        subagent_budget={"max_tool_calls": 1},
    )

    first = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"command": "git status --short"},
        },
    )
    second = await agent._acting(
        {
            "id": "tool-2",
            "name": "execute_shell_command",
            "input": {"command": "git status --short"},
        },
    )

    assert first == {"content": {"command": "git status --short"}}
    assert second is None
    assert "budget exceeded" in str(agent.printed[0].content)
