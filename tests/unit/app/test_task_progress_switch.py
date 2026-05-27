# -*- coding: utf-8 -*-
"""task progress source 开关的聚焦回归测试。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
    is_chat_task_progress_enabled,
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
        """执行轮次必须从后端持久化计划注入系统提示词。"""
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
            "accepted_plan": {
                "plan_id": "plan-123",
                "title": "Persisted plan",
                "summary": "Use backend facts",
                "steps": ["Read persisted step"],
                "risks": ["Known risk"],
                "verification": ["Run focused tests"],
                "open_questions": ["None"],
            },
        }

        with bind_source_system_config(_build_effective_config(False)):
            prompt = SWEAgent._build_sys_prompt(agent)

        assert "Accepted Plan Execution Context" in prompt
        assert "plan-123" in prompt
        assert "Read persisted step" in prompt
        assert "front-end query" in prompt

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
