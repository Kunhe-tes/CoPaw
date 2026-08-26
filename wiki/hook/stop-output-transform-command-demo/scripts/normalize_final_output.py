# -*- coding: utf-8 -*-
"""Stop 输出变换器的最小 command hook 样例。"""

from __future__ import annotations

import json
import sys
from typing import Any

_DRAFT_PREFIX = "DRAFT:"


def _load_payload() -> dict[str, Any]:
    """读取 hook runtime 通过 stdin 传入的 Stop HookContext。"""
    payload = json.loads(sys.stdin.read())
    if not isinstance(payload, dict):
        raise ValueError("hook payload must be an object")
    return payload


def _normalize_response(response: str) -> str:
    """去除草稿前缀和首尾空白，模拟最终文本规范化。"""
    normalized = response.strip()
    if normalized.startswith(_DRAFT_PREFIX):
        normalized = normalized.removeprefix(_DRAFT_PREFIX).lstrip()
    return normalized


def _build_output(payload: dict[str, Any]) -> dict[str, Any]:
    """仅在文本实际变化且非空时返回 replacementText。"""
    response = str(payload.get("assistant_response") or "")
    normalized = _normalize_response(response)
    output: dict[str, Any] = {
        "decision": "allow",
        "reason": "final output normalized",
    }
    if normalized and normalized != response:
        output["hookSpecificOutput"] = {
            "replacementText": normalized,
        }
    return output


def main() -> int:
    """执行脚本入口。"""
    try:
        output = _build_output(_load_payload())
    except Exception as exc:
        print(f"invalid hook payload: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
