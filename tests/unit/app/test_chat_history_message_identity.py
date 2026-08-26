# -*- coding: utf-8 -*-
"""Stable persisted history message identity coverage."""

from agentscope.message import Msg

from swe.app.runner.utils import agentscope_msg_to_message, legacy_message_id


def test_history_conversion_preserves_raw_message_id() -> None:
    raw = Msg(
        name="user",
        role="user",
        content="question",
        timestamp="2026-08-26T01:00:00Z",
    )
    raw.id = "raw-user-1"

    first = agentscope_msg_to_message([raw], session_id="session-1")
    second = agentscope_msg_to_message([raw], session_id="session-1")

    assert [message.id for message in first] == ["raw-user-1"]
    assert [message.id for message in second] == ["raw-user-1"]
    assert first[0].metadata["original_id"] == "raw-user-1"


def test_missing_raw_id_uses_deterministic_legacy_identity() -> None:
    raw = Msg(
        name="user",
        role="user",
        content="question",
        timestamp="2026-08-26T01:00:00Z",
    )
    raw.id = ""

    first = agentscope_msg_to_message([raw], session_id="session-1")
    second = agentscope_msg_to_message([raw], session_id="session-1")

    expected = legacy_message_id(
        "session-1",
        0,
        raw.timestamp,
        raw.role,
        raw.content,
    )
    assert first[0].id == second[0].id == expected
    assert first[0].id.startswith("legacy:")
