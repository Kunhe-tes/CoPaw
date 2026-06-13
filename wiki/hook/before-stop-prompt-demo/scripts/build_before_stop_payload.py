# -*- coding: utf-8 -*-
"""生成 BeforeStop prompt demo 的最小 HookContext 样本。"""

from __future__ import annotations

import json


def build_payload() -> dict[str, object]:
    """构造带 assistant_response 的结束前检查示例。"""
    return {
        "session_id": "demo-session",
        "transcript_path": "/tmp/demo-session.json",
        "cwd": "/workspace/project",
        "workspace_dir": "/workspace/project",
        "hook_event_name": "BeforeStop",
        "tenant_id": "default",
        "effective_tenant_id": "default",
        "user_id": "user-1",
        "agent_id": "demo-agent",
        "channel": "console",
        "prompt": "请帮我修改脚本并确认测试结果",
        "assistant_response": "我已经修改完成，测试也全部通过。",
        "tool_name": "execute_shell_command",
        "tool_input": {
            "command": "venv/bin/python -m pytest tests/unit/example.py",
        },
    }


def main() -> int:
    """把调试 payload 打印到 stdout。"""
    print(json.dumps(build_payload(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
