# -*- coding: utf-8 -*-
from __future__ import annotations

from swe.app.channels.console.channel import ConsoleChannel


async def _unused_process(_request):
    if _request is None:
        return
    yield None


def test_console_channel_uses_msgid_as_user_input_message_id() -> None:
    channel = ConsoleChannel(
        process=_unused_process,
        enabled=True,
        bot_prefix="Friday",
    )

    request = channel.build_agent_request_from_native(
        {
            "channel_id": "console",
            "sender_id": "user-1",
            "content_parts": [{"type": "text", "text": "hello"}],
            "meta": {
                "session_id": "session-1",
                "msgid": "question-msg-1",
            },
        },
    )

    assert request.input[0].id == "question-msg-1"
