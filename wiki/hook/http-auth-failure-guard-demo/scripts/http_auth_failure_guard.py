# -*- coding: utf-8 -*-
"""HTTP 鉴权失败后的阻断与上下文注入脚本。"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

AUTH_FAILURE_STATUS_CODES = {401, 403}
STATUS_FIELD_NAMES = ("status_code", "status", "statusCode", "code")
STATUS_TEXT_PATTERN = re.compile(
    r"(?:\bHTTP\b|\bstatus\b|\bcode\b|状态码)\D*(401|403)\b",
    re.IGNORECASE,
)


def _read_payload() -> dict[str, Any] | None:
    """读取 hook runtime 通过 stdin 传入的 JSON 对象。"""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("invalid hook payload", file=sys.stderr)
        return None

    if not isinstance(payload, dict):
        print("invalid hook payload", file=sys.stderr)
        return None
    return payload


def _coerce_status_code(value: Any) -> int | None:
    """把工具返回里的状态码字段归一为整数。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _find_status_in_mapping(mapping: dict[str, Any]) -> int | None:
    """从常见响应字段中查找 HTTP 状态码。"""
    for field_name in STATUS_FIELD_NAMES:
        status_code = _coerce_status_code(mapping.get(field_name))
        if status_code in AUTH_FAILURE_STATUS_CODES:
            return status_code
    return None


def _find_status_in_text(text: str) -> int | None:
    """从错误文本中识别 HTTP 401/403。"""
    match = STATUS_TEXT_PATTERN.search(text)
    if not match:
        return None
    return int(match.group(1))


def _extract_auth_failure_status(payload: dict[str, Any]) -> int | None:
    """从 HookContext 中提取鉴权失败状态码。"""
    tool_response = payload.get("tool_response")
    if isinstance(tool_response, dict):
        status_code = _find_status_in_mapping(tool_response)
        if status_code is not None:
            return status_code

    error = payload.get("error")
    if isinstance(error, str):
        return _find_status_in_text(error)
    return None


def _build_output(payload: dict[str, Any], status_code: int) -> dict[str, Any]:
    """构造 hook runtime 可识别的阻断输出。"""
    tool_name = str(payload.get("tool_name") or "目标工具")
    reason = f"工具 {tool_name} 返回 HTTP {status_code}，当前任务已失败。"
    context = (
        f"工具 {tool_name} 返回 HTTP {status_code}。请立即停止继续调用"
        "该接口或基于该接口结果推进任务，转而向用户说明当前接口"
        "鉴权失败，本次任务已经失败，需要先修复凭据或权限。"
    )
    return {
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "additionalContext": [context],
        },
    }


def main() -> int:
    """按 HookContext 判断是否需要阻断鉴权失败后的继续推进。"""
    payload = _read_payload()
    if payload is None:
        return 1

    event_name = payload.get("hook_event_name")
    if event_name not in {"PostToolUse", "PostToolUseFailure"}:
        print(json.dumps({}, ensure_ascii=False))
        return 0

    status_code = _extract_auth_failure_status(payload)
    output = _build_output(payload, status_code) if status_code else {}
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
