# -*- coding: utf-8 -*-
"""Tests for hidden Console context-reference message suffixes."""

from agentscope.message import Msg

from swe.app.runner.hidden_context_injection import (
    HIDDEN_CONTEXT_METADATA_KEY,
    append_hidden_context_to_user_message,
    redact_hidden_context_for_display,
)


def test_append_hidden_context_marks_model_facing_suffix() -> None:
    composed = append_hidden_context_to_user_message(
        Msg(name="alice", role="user", content="summarize this"),
        ["<TOOL-PREFERENCE>tool</TOOL-PREFERENCE>"],
    )

    assert composed.get_text_content() == (
        "summarize this\n\n<CONSOLE-HIDDEN-CONTEXT>\n"
        "<TOOL-PREFERENCE>tool</TOOL-PREFERENCE>\n"
        "</CONSOLE-HIDDEN-CONTEXT>"
    )
    assert composed.metadata[HIDDEN_CONTEXT_METADATA_KEY] == {
        "visible_text": "summarize this",
        "suffix": (
            "\n\n<CONSOLE-HIDDEN-CONTEXT>\n"
            "<TOOL-PREFERENCE>tool</TOOL-PREFERENCE>\n"
            "</CONSOLE-HIDDEN-CONTEXT>"
        ),
    }


def test_redact_hidden_context_returns_display_safe_copy() -> None:
    composed = append_hidden_context_to_user_message(
        Msg(name="alice", role="user", content="summarize this"),
        ["<SKILL-USE>skill</SKILL-USE>"],
    )

    redacted = redact_hidden_context_for_display(composed)

    assert redacted.get_text_content() == "summarize this"
    assert HIDDEN_CONTEXT_METADATA_KEY not in redacted.metadata
    assert "<SKILL-USE>" in composed.get_text_content()


def test_redact_hidden_context_fails_closed_when_stored_suffix_is_inconsistent() -> (
    None
):
    message = Msg(
        name="alice",
        role="user",
        content="visible\n\n<CONSOLE-HIDDEN-CONTEXT>unexpected",
        metadata={
            HIDDEN_CONTEXT_METADATA_KEY: {
                "visible_text": "visible",
                "suffix": "\n\n<CONSOLE-HIDDEN-CONTEXT>expected",
            },
        },
    )

    redacted = redact_hidden_context_for_display(message)

    assert redacted.get_text_content() == "visible"
