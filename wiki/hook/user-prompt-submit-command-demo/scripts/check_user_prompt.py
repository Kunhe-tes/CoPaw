# -*- coding: utf-8 -*-
"""UserPromptSubmit command hook 样例脚本。"""

from __future__ import annotations

import json
import sys

BLOCK_KEYWORDS = ("泄露密钥", "导出全部 token", "绕过审批")
MAX_TITLE_LENGTH = 24


def _load_payload() -> dict[str, object]:
    """读取并校验 hook runtime 传入的 JSON。"""
    raw = sys.stdin.read()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("hook payload must be an object")
    return data


def _build_session_title(prompt: str) -> str:
    """根据用户输入生成一个稳定且简短的标题。"""
    compact = " ".join(prompt.split())
    if not compact:
        return ""
    return compact[:MAX_TITLE_LENGTH]


def _build_output(prompt: str) -> dict[str, object]:
    """按 prompt 内容输出阻断或补充上下文。"""
    if not prompt.strip():
        return {}

    if any(keyword in prompt for keyword in BLOCK_KEYWORDS):
        return {
            "decision": "block",
            "reason": "用户输入命中了敏感操作预检查规则",
        }

    return {
        "hookSpecificOutput": {
            "sessionTitle": _build_session_title(prompt),
            "additionalContext": [
                "UserPromptSubmit hook 已检查当前输入，可继续进入主流程。",
                "如需更严格策略，可在脚本内继续细化关键词或结构化规则。",
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

    prompt = str(payload.get("prompt") or "")
    print(json.dumps(_build_output(prompt), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
