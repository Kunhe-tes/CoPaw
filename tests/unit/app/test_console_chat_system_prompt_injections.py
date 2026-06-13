# -*- coding: utf-8 -*-
"""验证 Console chat 请求会透传系统提示词注入字段。"""

from __future__ import annotations

from swe.app.routers.console import _extract_session_and_payload


def test_extract_session_and_payload_keeps_system_prompt_injections():
    payload = _extract_session_and_payload(
        {
            "channel": "console",
            "user_id": "alice",
            "session_id": "chat-1",
            "input": [],
            "system_prompt_injections": [
                "request prompt",
            ],
        },
    )

    assert payload["meta"]["system_prompt_injections"] == [
        "request prompt",
    ]
