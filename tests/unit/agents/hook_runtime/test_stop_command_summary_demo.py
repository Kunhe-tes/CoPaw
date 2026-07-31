# -*- coding: utf-8 -*-
"""验证 Stop 命令样例记录审计后批准完成。"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "wiki/hook/stop-command-summary-demo/scripts/finalize_stop_summary.py"
)


def _run_script(
    payload: Mapping[str, object],
) -> subprocess.CompletedProcess[str]:
    """执行目标脚本并返回进程结果。"""
    return subprocess.run(
        ["python", str(SCRIPT_PATH)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


def test_stop_demo_observes_payload_and_returns_allow() -> None:
    """普通回复和复核哨兵都会产生审计记录并批准完成。"""
    for payload in (
        {"tool_name": "search", "assistant_response": "任务完成"},
        {
            "tool_name": "deploy",
            "assistant_response": "WAIT_FOR_REVIEW",
        },
    ):
        result = _run_script(payload)

        assert result.returncode == 0
        assert json.loads(result.stdout) == {
            "decision": "allow",
            "reason": "summary recorded",
        }
        audit_record = json.loads(result.stderr)
        assert audit_record["event"] == "Stop"
        assert audit_record["tool_name"] == payload["tool_name"]
        assert audit_record["review_sentinel_detected"] == (
            payload["assistant_response"] == "WAIT_FOR_REVIEW"
        )
