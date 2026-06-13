# -*- coding: utf-8 -*-
"""MCP 工具失败后的统一兜底输出脚本。"""

from __future__ import annotations

import json
import sys

FALLBACK_MESSAGE = (
    "MCP 工具调用失败。请不要继续依赖本次工具结果，改为向用户说明"
    "当前调用暂时失败，并使用统一兜底话术回复。"
)


def main() -> int:
    """读取 Hook 载荷并根据失败场景输出兜底上下文。"""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("invalid hook payload", file=sys.stderr)
        return 1

    if not isinstance(payload, dict):
        print("invalid hook payload", file=sys.stderr)
        return 1

    event_name = payload.get("hook_event_name")
    error_value = payload.get("error")
    error_text = error_value.strip() if isinstance(error_value, str) else ""

    output = {}
    if event_name == "PostToolUseFailure" and error_text:
        output = {
            "hookSpecificOutput": {
                "additionalContext": [FALLBACK_MESSAGE],
            },
        }

    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
