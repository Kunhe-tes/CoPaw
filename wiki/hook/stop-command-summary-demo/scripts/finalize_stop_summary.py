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
    """记录审计后明确批准当前候选回复完成。"""
    del payload
    return {
        "decision": "allow",
        "reason": "summary recorded",
    }


def _build_audit_record(payload: dict[str, object]) -> dict[str, object]:
    """构造给外部日志采集器消费的 Stop 审计记录。"""
    tool_name = str(payload.get("tool_name") or "")
    return {
        "event": "Stop",
        "tool_name": tool_name or "unknown",
        "review_sentinel_detected": REVIEW_SENTINEL
        in str(payload.get("assistant_response") or ""),
    }


def main() -> int:
    """执行脚本入口。"""
    try:
        payload = _load_payload()
    except Exception as exc:
        print(f"invalid hook payload: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(_build_audit_record(payload), ensure_ascii=False),
        file=sys.stderr,
    )
    print(json.dumps(_build_output(payload), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
