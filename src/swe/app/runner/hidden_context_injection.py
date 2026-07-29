# -*- coding: utf-8 -*-
"""Compose and redact persisted hidden Console context directives."""

from __future__ import annotations

from typing import Iterable

from agentscope.message import Msg

HIDDEN_CONTEXT_METADATA_KEY = "console_hidden_context_v1"
_OPENING_TAG = "<CONSOLE-HIDDEN-CONTEXT>"
_CLOSING_TAG = "</CONSOLE-HIDDEN-CONTEXT>"


def _copy_message(
    message: Msg,
    *,
    content: str,
    metadata: dict,
) -> Msg:
    payload = message.to_dict()
    payload["content"] = content
    payload["metadata"] = metadata
    return Msg.from_dict(payload)


def append_hidden_context_to_user_message(
    message: Msg,
    directives: Iterable[str],
) -> Msg:
    """Append trusted directives to a user message and mark their suffix."""
    rendered = [
        directive.strip() for directive in directives if directive.strip()
    ]
    if not rendered:
        return message

    visible_text = message.get_text_content()
    suffix = (
        f"\n\n{_OPENING_TAG}\n" f"{'\n\n'.join(rendered)}\n" f"{_CLOSING_TAG}"
    )
    metadata = dict(message.metadata or {})
    metadata[HIDDEN_CONTEXT_METADATA_KEY] = {
        "visible_text": visible_text,
        "suffix": suffix,
    }
    return _copy_message(
        message,
        content=visible_text + suffix,
        metadata=metadata,
    )


def redact_hidden_context_for_display(message: Msg) -> Msg:
    """Return a display-safe copy when a message carries hidden context."""
    metadata = dict(message.metadata or {})
    marker = metadata.pop(HIDDEN_CONTEXT_METADATA_KEY, None)
    if not isinstance(marker, dict):
        return message

    visible_text = marker.get("visible_text")
    suffix = marker.get("suffix")
    if not isinstance(visible_text, str) or not isinstance(suffix, str):
        return message

    # An inconsistent marker can indicate corrupted persisted data.  Never
    # expose a possible internal suffix in that case.
    if message.get_text_content() != visible_text + suffix:
        return _copy_message(
            message,
            content=visible_text,
            metadata=metadata,
        )
    return _copy_message(
        message,
        content=visible_text,
        metadata=metadata,
    )


__all__ = [
    "HIDDEN_CONTEXT_METADATA_KEY",
    "append_hidden_context_to_user_message",
    "redact_hidden_context_for_display",
]
