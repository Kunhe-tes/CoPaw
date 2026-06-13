# -*- coding: utf-8 -*-
"""生成 SessionStart prompt demo 的最小 HookContext 样本。"""

from __future__ import annotations

import json


def build_payload() -> dict[str, object]:
    """构造一份便于人工调试的 HookContext 示例。"""
    return {
        "session_id": "demo-session",
        "transcript_path": "/tmp/demo-session.json",
        "cwd": "/workspace/project",
        "workspace_dir": "/workspace/project",
        "hook_event_name": "SessionStart",
        "tenant_id": "default",
        "effective_tenant_id": "default",
        "user_id": "user-1",
        "agent_id": "demo-agent",
        "channel": "console",
        "source": "startup",
        "model": "openai/gpt-5.4",
    }


def main() -> int:
    """把调试 payload 直接打印到 stdout。"""
    print(json.dumps(build_payload(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
