# -*- coding: utf-8 -*-
"""task progress source 开关的聚焦回归测试。"""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model._model_response import ChatResponse

from swe.agents import react_agent as react_agent_module
from swe.agents.react_agent import SWEAgent
from swe.agents.tools.update_task_progress import update_task_progress
from swe.app.runner.task_progress import (
    attach_task_progress,
    normalize_task_progress_payload,
)
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.registry import (
    build_default_source_system_config_payload,
    is_chat_task_progress_enabled,
    is_normal_mode_plan_interaction_tools_enabled,
)
from swe.app.source_system_config.runtime import bind_source_system_config
from swe.config.context import (
    reset_current_task_progress_chat_id,
    reset_current_task_progress_tracker,
    reset_current_task_progress_turn_id,
    set_current_task_progress_chat_id,
    set_current_task_progress_tracker,
    set_current_task_progress_turn_id,
)


def _build_effective_config(enabled: bool) -> EffectiveSourceSystemConfig:
    """构造带 task progress 开关的 effective config。"""
    return EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate(
            {
                "feature_switches": {
                    "chat_task_progress_enabled": enabled,
                },
            },
        ),
        version=1,
    )


def _build_plan_interaction_tools_config(
    enabled: bool,
) -> EffectiveSourceSystemConfig:
    return EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate(
            {
                "feature_switches": {
                    "normal_mode_plan_interaction_tools_enabled": enabled,
                },
            },
        ),
        version=1,
    )


class TestReactAgentTaskProgressPrompt:
    """验证 source 开关对系统提示词的影响。"""

    def _build_agent(self) -> SWEAgent:
        """创建仅供 `_build_sys_prompt` 使用的最小 Agent 桩。"""
        agent = object.__new__(SWEAgent)
        agent._request_context = {}
        agent._workspace_dir = Path(".")
        agent._env_context = None
        agent._agent_config = SimpleNamespace(heartbeat=None)
        return agent

    def test_rebuild_sys_prompt_skips_file_reads_when_freshness_unchanged(
        self,
        monkeypatch,
    ):
        """未变化时不重读 prompt 文件，但仍修正 session memory 系统消息。"""
        agent = self._build_agent()
        agent._sys_prompt = "cached prompt"
        agent._sys_prompt_freshness_token = ("same",)
        agent.memory = SimpleNamespace(
            content=[
                (Msg(name="system", role="system", content="stale"), []),
            ],
        )
        monkeypatch.setattr(
            SWEAgent,
            "_current_system_prompt_freshness_token",
            lambda _agent: ("same",),
        )

        def fail_build(_agent):
            raise AssertionError("system prompt should be reused")

        monkeypatch.setattr(SWEAgent, "_build_sys_prompt", fail_build)

        SWEAgent.rebuild_sys_prompt(agent)

        assert agent.memory.content[0][0].content == "cached prompt"

    def test_rebuild_sys_prompt_rebuilds_after_prompt_file_changes(
        self,
        tmp_path,
        monkeypatch,
    ):
        """prompt 文件变更后应重新构建并更新 session memory。"""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("first prompt", encoding="utf-8")
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()
        agent._workspace_dir = tmp_path
        agent._agent_config = SimpleNamespace(
            heartbeat=None,
            system_prompt_files=["AGENTS.md"],
        )
        with bind_source_system_config(_build_effective_config(False)):
            agent._sys_prompt = SWEAgent._build_sys_prompt(agent)
            agent._sys_prompt_freshness_token = (
                SWEAgent._current_system_prompt_freshness_token(agent)
            )
        agent.memory = SimpleNamespace(
            content=[
                (Msg(name="system", role="system", content="stale"), []),
            ],
        )
        agents_md.write_text(
            "second prompt with changed content",
            encoding="utf-8",
        )

        with bind_source_system_config(_build_effective_config(False)):
            SWEAgent.rebuild_sys_prompt(agent)

        assert "second prompt with changed content" in agent._sys_prompt
        assert agent.memory.content[0][0].content == agent._sys_prompt

    def test_rebuild_sys_prompt_rebuilds_after_active_model_changes(
        self,
        monkeypatch,
    ):
        """模型能力指纹变化后应重新构建 multimodal 相关提示词。"""
        agent = self._build_agent()
        monkeypatch.setattr(
            SWEAgent,
            "_active_model_prompt_token",
            lambda _agent: ("provider-a", "model-a", False, False, False),
        )
        with bind_source_system_config(_build_effective_config(False)):
            agent._sys_prompt = "cached prompt"
            agent._sys_prompt_freshness_token = (
                SWEAgent._current_system_prompt_freshness_token(agent)
            )
        agent.memory = SimpleNamespace(
            content=[
                (Msg(name="system", role="system", content="stale"), []),
            ],
        )
        monkeypatch.setattr(
            SWEAgent,
            "_active_model_prompt_token",
            lambda _agent: ("provider-a", "model-b", True, True, False),
        )

        def build_prompt(_agent):
            return "rebuilt prompt"

        monkeypatch.setattr(SWEAgent, "_build_sys_prompt", build_prompt)

        with bind_source_system_config(_build_effective_config(False)):
            SWEAgent.rebuild_sys_prompt(agent)

        assert agent._sys_prompt == "rebuilt prompt"
        assert agent.memory.content[0][0].content == "rebuilt prompt"

    def test_build_sys_prompt_skips_task_progress_when_disabled(
        self,
        monkeypatch,
    ):
        """关闭开关后，系统提示词不应继续强制要求调用工具。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()

        with bind_source_system_config(_build_effective_config(False)):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert "Task Progress Requirement" not in prompt
        assert "update_task_progress" not in prompt

    def test_build_sys_prompt_keeps_task_progress_when_enabled(
        self,
        monkeypatch,
    ):
        """开启开关时应保留原有 task progress 提示词约束。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()

        with bind_source_system_config(_build_effective_config(True)):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert "Task Progress Requirement" in prompt
        assert "update_task_progress" in prompt

    def test_build_sys_prompt_suppresses_task_progress_in_plan_mode(
        self,
        monkeypatch,
    ):
        """Plan Mode 工具箱不含进度工具，因此提示词也不能强制调用。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()
        agent._request_context = {"plan_mode_enabled": True}

        with bind_source_system_config(_build_effective_config(True)):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert "Task Progress Requirement" not in prompt
        assert "update_task_progress" not in prompt

    def test_build_sys_prompt_adds_plan_mode_clarification_instruction(
        self,
        monkeypatch,
    ):
        """Plan Mode 应要求分组澄清完整决策树后再提交计划。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()
        agent._request_context = {"plan_mode_enabled": True}

        with bind_source_system_config(_build_effective_config(False)):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert "You are now in Plan Mode" in prompt
        assert "MUST use ask_plan_clarification" in prompt
        assert "before calling submit_proposed_plan" in prompt
        assert "question series" in prompt
        assert "single_choice and multi_choice clarifications" in prompt
        assert "must not include recommended answers" in prompt
        assert "text clarifications may include a recommended answer" in prompt
        assert "After the user answers one question series" in prompt
        assert "all decision-tree branches" in prompt

    def test_build_sys_prompt_omits_plan_mode_instruction_in_normal_mode(
        self,
        monkeypatch,
    ):
        """普通模式不应携带 Plan Mode 的强追问指令。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()

        with bind_source_system_config(
            _build_plan_interaction_tools_config(True),
        ):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert "use ask_plan_clarification tool" not in prompt
        assert "Walk down each branch of the design tree" not in prompt

    def test_build_sys_prompt_appends_env_context_after_base_and_hint(
        self,
        monkeypatch,
    ):
        """运行时上下文仍应按既有顺序拼接在末尾。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "multimodal hint",
        )
        agent = self._build_agent()
        agent._env_context = (
            "====================\n"
            "- Source ID: portal\n"
            "- Current time: 2026-05-21 12:34:56 Asia/Shanghai (Thursday)\n"
            "===================="
        )

        with bind_source_system_config(_build_effective_config(False)):
            prompt = SWEAgent._build_sys_prompt(agent)

        base_index = prompt.index("base prompt")
        hint_index = prompt.index("multimodal hint")
        env_index = prompt.index("- Source ID: portal")
        assert base_index < hint_index < env_index

    def test_build_sys_prompt_injects_accepted_plan_in_normal_mode(
        self,
        monkeypatch,
    ):
        """执行轮次不应再把 accepted plan 拼进系统提示词。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()
        agent._request_context = {
            "plan_mode_enabled": False,
            "accepted_plan_source": "server_plan_store",
            "accepted_plan": {
                "plan_id": "plan-123",
                "title": "Persisted plan",
                "summary": "Use backend facts",
                "steps": ["Read persisted step"],
                "risks": ["Known risk"],
                "verification": ["Run focused tests"],
            },
        }

        with bind_source_system_config(_build_effective_config(False)):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert prompt == "base prompt"

    def test_build_sys_prompt_skips_accepted_plan_without_server_source(
        self,
        monkeypatch,
    ):
        """缺少后端来源标记时不能把 accepted_plan 注入系统提示词。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()
        agent._request_context = {
            "plan_mode_enabled": False,
            "accepted_plan": {"plan_id": "plan-123"},
        }

        with bind_source_system_config(_build_effective_config(False)):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert "Accepted Plan Execution Context" not in prompt

    def test_build_sys_prompt_skips_accepted_plan_in_plan_mode(
        self,
        monkeypatch,
    ):
        """计划评审阶段不能把 accepted_plan 当作执行上下文。"""
        monkeypatch.setattr(
            react_agent_module,
            "build_system_prompt_from_working_dir",
            lambda **_: "base prompt",
        )
        monkeypatch.setattr(
            react_agent_module,
            "build_multimodal_hint",
            lambda: "",
        )
        agent = self._build_agent()
        agent._request_context = {
            "plan_mode_enabled": True,
            "accepted_plan_source": "server_plan_store",
            "accepted_plan": {"plan_id": "plan-123"},
        }

        with bind_source_system_config(_build_effective_config(False)):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert "Accepted Plan Execution Context" not in prompt


class TestUpdateTaskProgressSwitch:
    """验证工具与 stream 附加都受 source 开关控制。"""

    @pytest.mark.asyncio
    async def test_update_task_progress_becomes_noop_when_disabled(self):
        """关闭开关后，工具调用应直接跳过且不触发 tracker。"""
        tracker = AsyncMock()
        tracker.get_task_progress = AsyncMock()
        tracker.update_task_progress = AsyncMock()
        tracker_token = set_current_task_progress_tracker(tracker)
        chat_token = set_current_task_progress_chat_id("chat-1")
        turn_token = set_current_task_progress_turn_id("turn-1")

        try:
            with bind_source_system_config(_build_effective_config(False)):
                response = await update_task_progress(
                    title="任务",
                    items=[{"label": "分析", "status": "running"}],
                )
        finally:
            reset_current_task_progress_tracker(tracker_token)
            reset_current_task_progress_chat_id(chat_token)
            reset_current_task_progress_turn_id(turn_token)

        tracker.get_task_progress.assert_not_awaited()
        tracker.update_task_progress.assert_not_awaited()
        assert response.content[0]["text"] == (
            '{"ok":true,"skipped":true,"reason":"task progress disabled"}'
        )

    @pytest.mark.asyncio
    async def test_update_task_progress_accepts_missing_title(self):
        """The tool schema says title is optional, so items-only calls should work."""
        tracker = AsyncMock()
        tracker.get_task_progress = AsyncMock(return_value=None)
        tracker.update_task_progress = AsyncMock()
        tracker_token = set_current_task_progress_tracker(tracker)
        chat_token = set_current_task_progress_chat_id("chat-1")
        turn_token = set_current_task_progress_turn_id("turn-1")

        try:
            with bind_source_system_config(_build_effective_config(True)):
                response = await update_task_progress(
                    items=[{"label": "分析", "status": "running"}],
                )
        finally:
            reset_current_task_progress_tracker(tracker_token)
            reset_current_task_progress_chat_id(chat_token)
            reset_current_task_progress_turn_id(turn_token)

        tracker.update_task_progress.assert_awaited_once()
        _chat_id, payload = tracker.update_task_progress.await_args.args
        assert response.content[0]["text"] == '{"ok":true}'
        assert payload.title is None
        assert payload.items[0].label == "分析"

    def test_attach_task_progress_skips_payload_when_disabled(self):
        """runner 附加阶段在开关关闭时不应把 task_progress 带给前端。"""
        event = {"type": "delta"}
        payload = normalize_task_progress_payload(
            turn_id="turn-1",
            title="任务",
            items=[{"label": "分析", "status": "running"}],
            current_step_index=1,
            version=1,
            phase_status="active",
        )

        assert (
            attach_task_progress(
                event,
                payload,
                enabled=False,
            )
            is event
        )


class _CaptureFormatter:
    """捕获 `_reasoning` 输入消息，避免依赖具体 Provider 格式化细节。"""

    def __init__(self) -> None:
        self.last_msgs = []

    async def format(self, msgs):
        self.last_msgs = list(msgs)
        return [{"role": "system", "content": "formatted"}]


@pytest.mark.asyncio
async def test_reasoning_injects_accepted_plan_as_internal_tool_exchange():
    """accepted plan 应以内联 tool exchange 注入当前推理轮次。"""
    agent = object.__new__(SWEAgent)
    agent.__dict__["_module_dict"] = {}
    agent.name = "Friday"
    agent._sys_prompt = "base prompt"
    agent._instance_pre_reasoning_hooks = {}
    agent._instance_post_reasoning_hooks = {}
    SWEAgent._class_pre_reasoning_hooks = {}
    SWEAgent._class_post_reasoning_hooks = {}
    agent.plan_notebook = None
    agent.print_hint_msg = False
    agent.compression_config = None
    agent.tts_model = None
    agent.model = AsyncMock(
        return_value=ChatResponse(
            id="resp-1",
            content=[{"type": "text", "text": "done"}],
        ),
    )
    agent.model.stream = False
    agent.formatter = _CaptureFormatter()
    agent.toolkit = SimpleNamespace(
        get_json_schemas=lambda: [],
        get_agent_skill_prompt=lambda: "",
    )
    agent.memory = InMemoryMemory()
    agent._request_context = {
        "turn_id": "turn-1",
        "plan_mode_enabled": False,
        "accepted_plan_source": "server_plan_store",
        "accepted_plan": {
            "plan_id": "plan-123",
            "title": "Persisted plan",
            "steps": ["Read persisted step"],
        },
    }
    agent._in_summarizing = False
    agent.agent_phase = lambda *_args, **_kwargs: nullcontext()
    agent._proactive_strip_media_blocks = lambda: 0
    agent._strip_media_blocks_from_memory = lambda: 0
    agent._is_bad_request_or_media_error = lambda _exc: False
    agent.print = AsyncMock()

    await agent.memory.add(Msg("user", "execute now", "user"))

    msg = await SWEAgent._reasoning(agent)

    assert msg.role == "assistant"
    prompt_msgs = agent.formatter.last_msgs
    assert [item.role for item in prompt_msgs[:4]] == [
        "system",
        "user",
        "assistant",
        "system",
    ]
    assert prompt_msgs[0].content == "base prompt"
    assert prompt_msgs[2].content[0]["type"] == "tool_use"
    assert prompt_msgs[3].content[0]["type"] == "tool_result"
    assert prompt_msgs[2].content[0]["id"] == prompt_msgs[3].content[0]["id"]
    assert prompt_msgs[2].content[0]["name"] == "accepted_plan_context"
    assert "Accepted Plan Execution Context" in (
        prompt_msgs[3].content[0]["output"][0]["text"]
    )
    assert "plan-123" in prompt_msgs[3].content[0]["output"][0]["text"]
    assert "front-end query" in prompt_msgs[3].content[0]["output"][0]["text"]
    assert not any(
        isinstance(item.content, str)
        and "Accepted Plan Execution Context" in item.content
        for item in prompt_msgs
    )
    assert [item[0].role for item in agent.memory.content] == [
        "user",
        "assistant",
    ]


@pytest.mark.asyncio
async def test_reasoning_skips_untrusted_accepted_plan_context():
    """缺少后端来源标记时，accepted plan 不得进入 tool exchange。"""
    agent = object.__new__(SWEAgent)
    agent.__dict__["_module_dict"] = {}
    agent.name = "Friday"
    agent._sys_prompt = "base prompt"
    agent._instance_pre_reasoning_hooks = {}
    agent._instance_post_reasoning_hooks = {}
    SWEAgent._class_pre_reasoning_hooks = {}
    SWEAgent._class_post_reasoning_hooks = {}
    agent.plan_notebook = None
    agent.print_hint_msg = False
    agent.compression_config = None
    agent.tts_model = None
    agent.model = AsyncMock(
        return_value=ChatResponse(
            id="resp-1",
            content=[{"type": "text", "text": "done"}],
        ),
    )
    agent.model.stream = False
    agent.formatter = _CaptureFormatter()
    agent.toolkit = SimpleNamespace(
        get_json_schemas=lambda: [],
        get_agent_skill_prompt=lambda: "",
    )
    agent.memory = InMemoryMemory()
    agent._request_context = {
        "turn_id": "turn-2",
        "plan_mode_enabled": False,
        "accepted_plan": {"plan_id": "client-plan"},
    }
    agent._in_summarizing = False
    agent.agent_phase = lambda *_args, **_kwargs: nullcontext()
    agent._proactive_strip_media_blocks = lambda: 0
    agent._strip_media_blocks_from_memory = lambda: 0
    agent._is_bad_request_or_media_error = lambda _exc: False
    agent.print = AsyncMock()

    await agent.memory.add(Msg("user", "execute now", "user"))

    await SWEAgent._reasoning(agent)

    assert [item.role for item in agent.formatter.last_msgs] == [
        "system",
        "user",
    ]


def test_is_chat_task_progress_enabled_reads_false_string_as_disabled():
    """兼容历史脏值时，字符串 false 不应再被 bool() 误判为开启。"""
    assert (
        is_chat_task_progress_enabled(
            {
                "feature_switches": {
                    "chat_task_progress_enabled": "false",
                },
            },
        )
        is False
    )


def test_plan_interaction_tools_switch_is_disabled_by_default():
    """普通模式计划交互工具必须在 Source 配置中默认关闭。"""
    assert build_default_source_system_config_payload()[
        "feature_switches"
    ] == {
        "chat_task_progress_enabled": True,
        "database_access_guard_enabled": True,
        "normal_mode_plan_interaction_tools_enabled": False,
    }


def test_plan_interaction_tools_switch_helper_reads_source_value():
    """helper 应读取并容错处理 Source 的成对工具开关。"""
    assert is_normal_mode_plan_interaction_tools_enabled(None) is False
    assert (
        is_normal_mode_plan_interaction_tools_enabled(
            {
                "feature_switches": {
                    "normal_mode_plan_interaction_tools_enabled": "true",
                },
            },
        )
        is True
    )
