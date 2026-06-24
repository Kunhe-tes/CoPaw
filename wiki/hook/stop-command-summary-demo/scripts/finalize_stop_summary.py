# -*- coding: utf-8 -*-
"""Stop command hook 样例脚本。"""

from __future__ import annotations

import json
import sys

REVIEW_SENTINEL = "WAIT_FOR_REVIEW"


def _load_payload() -> dict[str, object]:
    """读取 hook runtime 传入的 JSON。"""
    raw = sys.stdin.read()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("hook payload must be an object")
    return data


def _build_output(payload: dict[str, object]) -> dict[str, object]:
    """根据 assistant_response 生成 Stop 事件输出。"""
    response_text = str(payload.get("assistant_response") or "")
    if REVIEW_SENTINEL in response_text:
        return {
            "continue": False,
            "stopReason": "候选回复显式要求等待人工复核，本轮在 Stop 阶段结束",
        }

    tool_name = str(payload.get("tool_name") or "")
    return {
        "hookSpecificOutput": {
            "additionalContext": [
                "Stop hook 已执行最终收尾。",
                f"最后一次相关工具: {tool_name or 'unknown'}。",
            ],
        },
    }


def main() -> int:
    """执行脚本入口。"""
    try:
        payload = _load_payload()
    except Exception as exc:
        print(f"invalid hook payload: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(_build_output(payload), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
