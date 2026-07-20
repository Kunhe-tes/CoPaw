# -*- coding: utf-8 -*-
"""验证 Console chat 请求会透传系统提示词注入字段。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from swe.app.routers import console as console_router
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


def test_extract_session_and_payload_keeps_selected_skill_names_for_console():
    payload = _extract_session_and_payload(
        {
            "channel": "feishu",
            "user_id": "alice",
            "session_id": "chat-1",
            "input": [],
            "selected_skill_names": ["guide", "guide", "review"],
        },
    )

    assert payload["channel_id"] == "console"
    assert payload["meta"]["selected_skill_names"] == [
        "guide",
        "guide",
        "review",
    ]


def test_extract_session_and_payload_reads_selected_skill_names_from_request_meta():
    fake_request = SimpleNamespace(
        channel="feishu",
        user_id="alice",
        session_id="chat-1",
        input=[],
        channel_meta={"selected_skill_names": ["guide"]},
    )
    with patch.object(console_router, "AgentRequest", SimpleNamespace):
        payload = _extract_session_and_payload(fake_request)

    assert payload["channel_id"] == "console"
    assert payload["meta"]["selected_skill_names"] == ["guide"]
