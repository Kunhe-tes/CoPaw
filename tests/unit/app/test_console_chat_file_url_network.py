# -*- coding: utf-8 -*-
"""验证 Console chat 请求会透传静态文件 URL 网络字段。"""

from __future__ import annotations

from swe.app.routers.console import _extract_session_and_payload


def test_extract_session_and_payload_keeps_file_url_network():
    payload = _extract_session_and_payload(
        {
            "channel": "console",
            "user_id": "alice",
            "session_id": "chat-1",
            "input": [],
            "file_url_network": "business",
        },
    )

    assert payload["meta"]["file_url_network"] == "business"
