# -*- coding: utf-8 -*-
"""验证 MCP 调用失败兜底脚本的行为。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from swe.agents.hook_runtime.models import HookEventName, HookSessionState
from swe.agents.hook_runtime.skill_loader import load_skill_hooks_for_session

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "wiki/hook/mcp-failure-fallback-demo/scripts/mcp_failure_fallback.py"
)


def _run_script(payload: str) -> subprocess.CompletedProcess[str]:
    """执行目标脚本并返回进程结果。"""
    return subprocess.run(
        ["python", str(SCRIPT_PATH)],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )


def test_returns_additional_context_for_failure_with_error() -> None:
    """PostToolUseFailure 且 error 非空时返回 additionalContext。"""
    payload = {
        "hook_event_name": "PostToolUseFailure",
        "error": " tool call failed ",
    }

    result = _run_script(json.dumps(payload, ensure_ascii=False))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "hookSpecificOutput": {
            "additionalContext": [
                (
                    "MCP 工具调用失败。请不要继续依赖本次工具结果，改为向用户说明"
                    "当前调用暂时失败，并使用统一兜底话术回复。"
                ),
            ],
        },
    }


def test_returns_empty_object_when_error_is_blank() -> None:
    """PostToolUseFailure 但 error 为空时返回空对象。"""
    payload = {
        "hook_event_name": "PostToolUseFailure",
        "error": "   ",
    }

    result = _run_script(json.dumps(payload, ensure_ascii=False))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {}


def test_returns_empty_object_for_non_failure_event() -> None:
    """非 PostToolUseFailure 事件时返回空对象。"""
    payload = {
        "hook_event_name": "PreToolUse",
        "error": "network error",
    }

    result = _run_script(json.dumps(payload, ensure_ascii=False))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {}


def test_invalid_json_exits_with_code_one_and_stderr() -> None:
    """非法 JSON 输入时返回码为 1 且 stderr 包含固定文案。"""
    result = _run_script("{invalid-json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "invalid hook payload" in result.stderr


def test_non_dict_payload_exits_with_code_one_and_stderr() -> None:
    """根对象不是 dict 时返回码为 1 且 stderr 包含固定文案。"""
    result = _run_script(json.dumps(["not", "dict"], ensure_ascii=False))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "invalid hook payload" in result.stderr


def test_demo_skill_hook_config_loads_from_repo_files() -> None:
    """验证 demo skill 的 hooks 配置可从仓库文件加载并完成命名空间归一。"""
    skill_root = REPO_ROOT / "wiki/hook/mcp-failure-fallback-demo"

    result = load_skill_hooks_for_session(
        skill_name="mcp-failure-fallback-demo",
        skill_root=skill_root,
        workspace_dir=REPO_ROOT,
        session_state=HookSessionState(),
    )

    source = result.loaded_skill_sources[0]
    assert set(source.hook_config.events.keys()) == {
        HookEventName.STOP,
        HookEventName.POST_TOOL_USE_FAILURE,
    }

    stop_group = source.hook_config.events[HookEventName.STOP][0]
    stop_handler = stop_group.hooks[0]
    assert (
        stop_group.id
        == "skill:mcp-failure-fallback-demo:mcp-response-consistency-check"
    )
    assert stop_handler.id == (
        "skill:mcp-failure-fallback-demo:" "mcp-response-consistency-judge"
    )
    assert stop_handler.type == "prompt"
    assert stop_handler.fail_policy == "allow"
    assert "assistant_response" in stop_handler.prompt
    assert "HookContext JSON" in stop_handler.prompt

    group = source.hook_config.events[HookEventName.POST_TOOL_USE_FAILURE][0]
    handler = group.hooks[0]
    assert source.source_id == "skill:mcp-failure-fallback-demo"
    assert group.id == "skill:mcp-failure-fallback-demo:mcp-failure-fallback"
    assert handler.id == "skill:mcp-failure-fallback-demo:mcp-failure-context"
    assert handler.cwd == str(skill_root.resolve())
    assert handler.fail_policy == "allow"
    assert handler.argv == [
        "python",
        str(
            (skill_root / "scripts" / "mcp_failure_fallback.py").resolve(),
        ),
    ]
