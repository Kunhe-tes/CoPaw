# -*- coding: utf-8 -*-
"""Integration seams between SubAgents, SWEAgent, and ToolGuardMixin."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentscope.tool import ToolResponse

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


class _PlanningToolkit:
    async def call_tool_function(self, tool_call):
        async def _chunks():
            yield ToolResponse(
                content=[
                    {
                        "type": "text",
                        "text": "Planning clarification requested.",
                    },
                ],
                metadata={
                    "plan_interaction_card": {
                        "card_type": "plan_clarification",
                        "kind": "form",
                        "prompt": tool_call["input"]["prompt"],
                        "form_id": "customer_operation_plan",
                        "fields": [
                            {
                                "id": "industry",
                                "label": "行业/业务类型",
                                "type": "select",
                                "options": [
                                    {
                                        "id": "SaaS/软件服务",
                                        "label": "SaaS/软件服务",
                                    },
                                ],
                                "required": True,
                            },
                        ],
                        "allow_custom_response": True,
                    },
                },
            )

        return _chunks()


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


class _FakePlanGuardAgent(ToolGuardMixin, _BaseAgent):
    name = "Friday"

    def __init__(self, tmp_path: Path):
        self._request_context = {
            "session_id": "session-1",
            "agent_role": "main",
            "plan_mode_enabled": True,
        }
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
        raise AssertionError("Plan Mode policy must not request approval")

    async def print(self, msg, *args, **kwargs):
        self.printed.append(msg)


class _FakePlanInteractionAgent(_FakePlanGuardAgent):
    def __init__(self, tmp_path: Path):
        super().__init__(tmp_path)
        self.toolkit = _PlanningToolkit()


class _FakeNormalMainGuardAgent(ToolGuardMixin, _BaseAgent):
    name = "Friday"

    def __init__(self, tmp_path: Path):
        self._request_context = {
            "session_id": "session-1",
            "agent_role": "main",
            "plan_mode_enabled": False,
            "accepted_plan": {
                "plan_id": "plan-1",
                "title": "Accepted plan",
            },
        }
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
        return {"content": "approval path"}

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


def test_main_agent_never_registers_delegation_tool(
    tmp_path: Path,
) -> None:
    """Synchronous delegation is no longer part of the Main Agent toolkit."""
    disabled = _bare_agent(tmp_path, request_context={"agent_role": "main"})
    enabled = _bare_agent(
        tmp_path,
        request_context={"agent_role": "main", "enable_subagents": True},
    )

    assert (
        "delegate_to_subagent" not in SWEAgent._create_toolkit(disabled).tools
    )
    assert (
        "delegate_to_subagent" not in SWEAgent._create_toolkit(enabled).tools
    )
    main_tools = SWEAgent._create_toolkit(disabled).tools
    assert "ask_plan_clarification" in main_tools
    assert "submit_proposed_plan" in main_tools
    assert (
        "ask_plan_clarification"
        not in SWEAgent._create_toolkit(
            _bare_agent(tmp_path, request_context={"agent_role": "subagent"}),
        ).tools
    )


def test_plan_mode_toolkit_excludes_mutating_tools(tmp_path: Path) -> None:
    """Plan Mode 只暴露规划所需的只读工具。"""
    agent = _bare_agent(
        tmp_path,
        request_context={"agent_role": "main", "plan_mode_enabled": True},
    )

    tools = SWEAgent._create_toolkit(agent).tools

    assert "read_file" in tools
    assert "grep_search" in tools
    assert "glob_search" in tools
    assert "get_current_time" in tools
    assert "execute_shell_command" in tools
    assert "ask_plan_clarification" in tools
    assert "submit_proposed_plan" in tools
    for tool_name in (
        "write_file",
        "edit_file",
        "copy_file_to_static",
        "update_task_progress",
        "set_user_timezone",
        "get_token_usage",
    ):
        assert tool_name not in tools


def test_plan_mode_shell_policy_allows_strict_readonly_commands(
    tmp_path: Path,
) -> None:
    """Plan Mode shell 仅允许参数可证明只读的简单命令。"""
    agent = _FakePlanGuardAgent(tmp_path)

    for command in (
        "pwd",
        "ls src",
        "rg accepted_plan src/swe",
        "grep -R accepted_plan src/swe",
        "git status --short",
        "git diff -- src/swe/app/plans/models.py",
        "git grep accepted_plan -- src/swe",
        "git log --oneline -5",
        "git show HEAD:README.md",
    ):
        assert (
            agent._plan_mode_policy_denial(
                "execute_shell_command",
                {"command": command},
            )
            is None
        ), command


def test_plan_mode_shell_policy_rejects_mutating_shell_bypasses(
    tmp_path: Path,
) -> None:
    """Plan Mode shell 默认拒绝复合语法和带写入能力的参数。"""
    agent = _FakePlanGuardAgent(tmp_path)

    for command in (
        "sed -i '' 's/foo/bar/' some-file.py",
        "git diff --output=/tmp/plan-mode-write.txt",
        "rg foo > out",
        "ls; touch x",
        "A=1 rg foo",
        "git show HEAD:foo > bar",
        "git diff --ext-diff",
    ):
        denial = agent._plan_mode_policy_denial(
            "execute_shell_command",
            {"command": command},
        )
        assert denial is not None, command


@pytest.mark.asyncio
async def test_plan_mode_hard_policy_allows_memory_and_clarification_tools(
    tmp_path: Path,
) -> None:
    """Plan Mode 可使用记忆检索和计划澄清工具补足规划上下文。"""
    agent = _FakePlanGuardAgent(tmp_path)

    for tool_name, tool_input in (
        ("memory_search", {"query": "prior decision"}),
        (
            "ask_plan_clarification",
            {"prompt": "Choose scope", "kind": "choice"},
        ),
    ):
        result = await agent._acting(
            {
                "id": f"tool-{tool_name}",
                "name": tool_name,
                "input": tool_input,
            },
        )

        assert result == {"content": tool_input}


@pytest.mark.asyncio
async def test_plan_interaction_tool_metadata_is_printed_and_persisted(
    tmp_path: Path,
) -> None:
    """计划交互卡片依赖消息 metadata，不能只保留工具文本输出。"""
    agent = _FakePlanInteractionAgent(tmp_path)

    result = await agent._acting(
        {
            "id": "tool-plan-1",
            "name": "ask_plan_clarification",
            "input": {
                "prompt": "制定客户经营计划需要明确几个方向，请告诉我：",
                "kind": "customer_operation_plan",
            },
        },
    )

    assert result is None
    assert agent.printed
    assert agent.printed[-1].metadata["plan_interaction_card"] == {
        "card_type": "plan_clarification",
        "kind": "form",
        "prompt": "制定客户经营计划需要明确几个方向，请告诉我：",
        "form_id": "customer_operation_plan",
        "fields": [
            {
                "id": "industry",
                "label": "行业/业务类型",
                "type": "select",
                "options": [
                    {
                        "id": "SaaS/软件服务",
                        "label": "SaaS/软件服务",
                    },
                ],
                "required": True,
            },
        ],
        "allow_custom_response": True,
    }
    assert (
        agent.memory.content[-1][0].metadata["plan_interaction_card"][
            "form_id"
        ]
        == "customer_operation_plan"
    )


def test_plan_mode_toolkit_excludes_synchronous_delegation(
    tmp_path: Path,
) -> None:
    """Plan Mode also uses background SubAgent tools, not sync delegation."""
    agent = _bare_agent(
        tmp_path,
        request_context={
            "agent_role": "main",
            "plan_mode_enabled": True,
            "enable_subagents": True,
        },
    )

    assert "delegate_to_subagent" not in SWEAgent._create_toolkit(agent).tools


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("write_file", {"file_path": "x", "content": "no"}),
        ("edit_file", {"file_path": "x", "old_str": "a", "new_str": "b"}),
        ("copy_file_to_static", {"file_path": "x"}),
        ("update_task_progress", {"tasks": []}),
        ("execute_shell_command", {"command": "pytest tests/unit"}),
        ("execute_shell_command", {"command": "git status > out.txt"}),
        ("execute_shell_command", {"command": "kubectl apply -f deploy.yaml"}),
        ("execute_shell_command", {"command": "alembic upgrade head"}),
    ],
)
async def test_plan_mode_hard_policy_denies_before_hooks_and_approvals(
    tmp_path: Path,
    tool_name: str,
    tool_input: dict,
) -> None:
    """Plan Mode 硬策略在 hooks 和审批前拒绝写入或验证命令。"""
    agent = _FakePlanGuardAgent(tmp_path)

    result = await agent._acting(
        {"id": "tool-1", "name": tool_name, "input": tool_input},
    )

    assert result is None
    assert agent._emit_tool_hook_called is False
    assert agent._acting_with_approval_called is False
    assert "blocked by Plan Mode policy" in str(agent.printed[0].content)


@pytest.mark.asyncio
async def test_plan_mode_hard_policy_allows_readonly_shell(
    tmp_path: Path,
) -> None:
    """只读 shell 命令仍进入正常工具执行路径。"""
    agent = _FakePlanGuardAgent(tmp_path)

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"command": "git status --short"},
        },
    )

    assert result == {"content": {"command": "git status --short"}}


@pytest.mark.asyncio
async def test_plan_mode_hard_policy_rechecks_hook_updated_input(
    tmp_path: Path,
) -> None:
    """Hook 改写后的输入不能绕过 Plan Mode 只读策略。"""
    agent = _FakePlanGuardAgent(tmp_path)

    async def _rewrite_to_test_command(*args, **kwargs):
        agent._emit_tool_hook_called = True
        return MergedHookResult(updated_input={"command": "pytest"})

    agent._emit_tool_hook = _rewrite_to_test_command

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "execute_shell_command",
            "input": {"command": "git status --short"},
        },
    )

    assert result is None
    assert agent._emit_tool_hook_called is True
    assert "blocked by Plan Mode policy" in str(agent.printed[0].content)


@pytest.mark.asyncio
async def test_plan_mode_denial_leaves_workspace_file_unchanged(
    tmp_path: Path,
) -> None:
    """Plan Mode 拦截写工具后不会进入任何可能改写工作区的路径。"""
    target = tmp_path / "target.txt"
    target.write_text("original", encoding="utf-8")
    agent = _FakePlanGuardAgent(tmp_path)

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "write_file",
            "input": {
                "file_path": str(target),
                "content": "mutated",
            },
        },
    )

    assert result is None
    assert target.read_text(encoding="utf-8") == "original"


@pytest.mark.asyncio
async def test_execute_turn_restores_normal_main_agent_tool_path(
    tmp_path: Path,
) -> None:
    """execute 决策后的 normal 轮次不再套用 Plan Mode 硬拒绝。"""
    agent = _FakeNormalMainGuardAgent(tmp_path)

    result = await agent._acting(
        {
            "id": "tool-1",
            "name": "write_file",
            "input": {
                "file_path": "target.txt",
                "content": "allowed by normal mode",
            },
        },
    )

    assert result == {
        "content": {
            "file_path": "target.txt",
            "content": "allowed by normal mode",
        },
    }
    assert agent.printed == []
