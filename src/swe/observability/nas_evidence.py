# -*- coding: utf-8 -*-
"""Link observed messages only after NAS has persisted the matching content."""

import hashlib
import json
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from .context import current_context
from .instrumentation import (
    SpanHandle,
    _current_tool_span,
    _pending_model_response_spans,
)

_pending: ContextVar[
    dict[tuple[str, str], tuple[SpanHandle, dict[str, Any]]] | None
] = ContextVar("nas_message_evidence", default=None)


@asynccontextmanager
async def collect_nas_evidence():
    token = _pending.set({})
    try:
        yield
    finally:
        _pending.reset(token)


def nas_reference(message):
    try:
        encoded = json.dumps(
            [message["id"], message["role"], message["content"]],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    except (KeyError, TypeError, ValueError):
        return None
    return "nas:" + hashlib.sha256(encoded).hexdigest()


def remember_nas_message(chat_id, message):
    pending = _pending.get()
    context = current_context()
    if pending is None or context is None:
        return
    blocks = message.content if isinstance(message.content, list) else []
    kinds = {block.get("type") for block in blocks if isinstance(block, dict)}
    state = "available"
    if "tool_result" in kinds:
        span = _current_tool_span.get()
        kind = "tool_output"
        if span and span.tool_output_was_compacted(message.id):
            state = "compacted"
    elif (
        message.role == "assistant"
        and "tool_use" not in kinds
        and (message.get_text_content() or "").strip()
    ):
        span = (_pending_model_response_spans.get() or {}).get(
            (context.obs_run_id, message.invocation_id),
        )
        kind = "assistant_answer"
    else:
        return
    if span is None or span._context.business_ref.get("chat_id") != chat_id:
        return
    reference = nas_reference(message.to_dict())
    if reference:
        pending[(chat_id, reference)] = (
            span,
            {
                "chat_id": chat_id,
                "message_id": message.id,
                "content_type": kind,
                "saved_state": state,
                "reference_id": reference,
            },
        )


def publish_nas_evidence(messages, *, chat_id=None):
    pending = _pending.get()
    if not pending:
        return
    known = {
        (attributes["message_id"], key[1]): key
        for key, (_, attributes) in pending.items()
        if chat_id is None or key[0] == chat_id
    }
    message_ids = {message_id for message_id, _ in known}
    for message in messages:
        if (
            not isinstance(message, dict)
            or message.get("id") not in message_ids
        ):
            continue
        key = known.get((message["id"], nas_reference(message)))
        candidate = pending.pop(key, None) if key is not None else None
        if candidate is not None:
            span, attributes = candidate
            span.event("evidence.linked", **attributes)
