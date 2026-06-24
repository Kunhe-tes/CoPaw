# -*- coding: utf-8 -*-
"""PreToolUse command hook 样例脚本。"""

from __future__ import annotations

import json
import sys


def _load_payload() -> dict[str, object]:
    """读取并校验 hook payload。"""
    raw = sys.stdin.read()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("hook payload must be an object")
    return data


def _extract_command(payload: dict[str, object]) -> str:
    """从 tool_input 中取出 shell command。"""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command")
    return str(command or "")


def _build_output(command: str) -> dict[str, object]:
    """根据命令内容生成不同的 hook 结果。"""
    normalized = command.strip()
    if not normalized:
        return {}

    if "rm -rf" in normalized:
        return {
            "hookSpecificOutput": {
                "permissionDecision": "deny",
                "permissionDecisionReason": "命令包含高风险删除操作",
            },
        }

    if normalized.startswith("git push"):
        return {
            "hookSpecificOutput": {
                "permissionDecision": "ask",
                "permissionDecisionReason": "该命令会影响远端仓库，请先审批",
            },
        }

    if normalized == "ls":
        return {
            "hookSpecificOutput": {
                "permissionDecision": "allow",
                "permissionDecisionReason": "自动为 ls 补全更常用的展示参数",
                "updatedInput": {
                    "command": "ls -la",
                },
            },
        }

    return {
        "hookSpecificOutput": {
            "permissionDecision": "allow",
            "permissionDecisionReason": "命令通过 demo 策略检查",
        },
    }


def main() -> int:
    """执行脚本入口。"""
    try:
        payload = _load_payload()
    except Exception as exc:
        print(f"invalid hook payload: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            _build_output(_extract_command(payload)),
            ensure_ascii=False,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
