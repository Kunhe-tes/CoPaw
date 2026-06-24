# -*- coding: utf-8 -*-
"""验证 HTTP 鉴权失败守卫 hook demo 的脚本和配置。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from swe.agents.hook_runtime.models import HookEventName, HookSessionState
from swe.agents.hook_runtime.skill_loader import load_skill_hooks_for_session

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "wiki/hook/http-auth-failure-guard-demo"
SCRIPT_PATH = SKILL_ROOT / "scripts/http_auth_failure_guard.py"


def _run_script(
    payload: dict[str, object] | str,
) -> subprocess.CompletedProcess[str]:
    """执行目标脚本并返回进程结果。"""
    input_text = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload, ensure_ascii=False)
    )
    return subprocess.run(
        ["python", str(SCRIPT_PATH)],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def test_blocks_failure_event_when_error_mentions_401() -> None:
    """失败事件包含 401 时返回 block 和额外上下文。"""
    result = _run_script(
        {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "call_protected_api",
            "error": "HTTP request failed with status 401 Unauthorized",
        },
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "decision": "block",
        "reason": "工具 call_protected_api 返回 HTTP 401，当前任务已失败。",
        "hookSpecificOutput": {
            "additionalContext": [
                (
                    "工具 call_protected_api 返回 HTTP 401。请立即停止继续调用"
                    "该接口或基于该接口结果推进任务，转而向用户说明当前接口"
                    "鉴权失败，本次任务已经失败，需要先修复凭据或权限。"
                ),
            ],
        },
    }


def test_blocks_success_event_when_response_contains_403() -> None:
    """成功事件的结构化返回体包含 403 时也返回 block。"""
    result = _run_script(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "call_protected_api",
            "tool_response": {
                "status_code": 403,
                "body": {"error": "forbidden"},
            },
        },
    )

    assert result.returncode == 0
    assert result.stderr == ""
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert (
        output["reason"]
        == "工具 call_protected_api 返回 HTTP 403，当前任务已失败。"
    )
    assert "HTTP 403" in output["hookSpecificOutput"]["additionalContext"][0]


def test_returns_empty_object_for_non_auth_error_status() -> None:
    """非鉴权错误状态码不触发此 demo 的守卫策略。"""
    result = _run_script(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "call_protected_api",
            "tool_response": {"status_code": 500},
        },
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {}


def test_invalid_json_exits_with_code_one_and_stderr() -> None:
    """非法 JSON 输入时返回码为 1 且 stderr 包含固定文案。"""
    result = _run_script("{invalid-json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "invalid hook payload" in result.stderr


def test_demo_skill_hook_config_loads_from_repo_files() -> None:
    """验证 demo skill 的 hooks 配置可加载并完成命名空间归一。"""
    result = load_skill_hooks_for_session(
        skill_name="http-auth-failure-guard-demo",
        skill_root=SKILL_ROOT,
        workspace_dir=REPO_ROOT,
        session_state=HookSessionState(),
    )

    source = result.loaded_skill_sources[0]
    assert set(source.hook_config.events.keys()) == {
        HookEventName.POST_TOOL_USE,
        HookEventName.POST_TOOL_USE_FAILURE,
    }

    for event_name in (
        HookEventName.POST_TOOL_USE,
        HookEventName.POST_TOOL_USE_FAILURE,
    ):
        group = source.hook_config.events[event_name][0]
        handler = group.hooks[0]
        assert group.matcher.tools == ["call_protected_api"]
        suffix = (
            "http-auth-failure-context-post-tool-use"
            if event_name == HookEventName.POST_TOOL_USE
            else "http-auth-failure-context-post-tool-use-failure"
        )
        assert handler.id == (
            "skill:http-auth-failure-guard-demo:" f"{suffix}"
        )
        assert handler.cwd == str(SKILL_ROOT.resolve())
        assert handler.fail_policy == "allow"
        assert handler.argv == [
            "python",
            str(SCRIPT_PATH.resolve()),
        ]
