"""External approval submission helpers.

These helpers let another channel approve or deny an existing console
approval by submitting the same ``/approve`` or ``/deny`` command that the
console UI would send.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentscope_runtime.engine.schemas.agent_schemas import (
    ContentType,
    TextContent,
)

from .service import PendingApproval

logger = logging.getLogger(__name__)

CONSOLE_CHANNEL = "console"
ZHAOHU_CHANNEL = "zhaohu"
APPROVAL_SOURCE_CHANNEL_META_KEY = "approval_source_channel"
APPROVAL_REQUEST_ID_META_KEY = "approval_request_id"
APPROVAL_DECISION_META_KEY = "approval_decision"
_RUN_IDLE_WAIT_SECONDS = 5.0
_RUN_IDLE_POLL_SECONDS = 0.05


class ExternalApprovalDecision(str, Enum):
    """Decision submitted by an external channel."""

    APPROVE = "approve"
    DENY = "deny"


@dataclass(frozen=True)
class ExternalApprovalSubmission:
    """Result of submitting an external approval decision."""

    request_id: str
    decision: ExternalApprovalDecision
    status: str
    session_id: str
    chat_id: str | None = None
    submitted: bool = False
    reconnect: bool = False
    is_new_run: bool = False

def _command_for_decision(
    decision: ExternalApprovalDecision,
    request_id: str,
) -> str:
    if decision == ExternalApprovalDecision.APPROVE:
        return f"/approve {request_id}"
    return f"/deny {request_id}"


def _status_for_decision(decision: ExternalApprovalDecision) -> str:
    if decision == ExternalApprovalDecision.APPROVE:
        return "approved"
    return "denied"


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _get_channel(channel_manager: Any, name: str) -> Any | None:
    if channel_manager is None:
        return None
    get_channel = getattr(channel_manager, "get_channel", None)
    if get_channel is None:
        return None
    return await _maybe_await(get_channel(name))


async def _wait_until_run_idle(task_tracker: Any, run_key: str) -> None:
    get_status = getattr(task_tracker, "get_status", None)
    if get_status is None:
        return

    deadline = asyncio.get_running_loop().time() + _RUN_IDLE_WAIT_SECONDS
    while True:
        status = await _maybe_await(get_status(run_key))
        if status in (None, "idle"):
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("approval chat is still streaming")
        await asyncio.sleep(_RUN_IDLE_POLL_SECONDS)


def build_external_approval_payload(
    *,
    pending: PendingApproval,
    decision: ExternalApprovalDecision,
    source_channel: str,
    source_user_id: str | None = None,
    source_message_id: str | None = None,
    source_id: str | None = None,
    user_name: str | None = None,
    bbk_id: str | None = None,
) -> dict[str, Any]:
    """Build the console-native payload for an external decision."""
    command = _command_for_decision(decision, pending.request_id)
    meta: dict[str, Any] = {
        "session_id": pending.session_id,
        "user_id": pending.user_id,
        APPROVAL_REQUEST_ID_META_KEY: pending.request_id,
        APPROVAL_DECISION_META_KEY: decision.value,
        APPROVAL_SOURCE_CHANNEL_META_KEY: source_channel,
    }
    if source_user_id:
        meta["approval_source_user_id"] = source_user_id
    if source_message_id:
        meta["approval_source_message_id"] = source_message_id
    if source_id:
        meta["source_id"] = source_id
    if user_name:
        meta["user_name"] = user_name
    if bbk_id:
        meta["bbk_id"] = bbk_id

    return {
        "channel_id": CONSOLE_CHANNEL,
        "sender_id": pending.user_id or "external-approval",
        "content_parts": [
            TextContent(type=ContentType.TEXT, text=command),
        ],
        "meta": meta,
    }


async def notify_cron_approval_pending(
    pending: PendingApproval,
    *,
    channel_manager: Any | None,
) -> None:
    """Notify zhaohu that a cron approval is pending.

    Zhaohu rendering is currently a no-op hook. This function keeps the
    workflow boundary in place so the real rich card implementation can fill
    it later.
    """
    zhaohu = await _get_channel(channel_manager, ZHAOHU_CHANNEL)
    if zhaohu is None:
        return
    sender = getattr(zhaohu, "send_cron_approval_card", None)
    if sender is None:
        return

    approval_meta = pending.extra if isinstance(pending.extra, dict) else {}
    tool_call = pending.extra.get("tool_call") if pending.extra else None
    tool_input = tool_call.get("input") if isinstance(tool_call, dict) else {}
    try:
        await sender(
            request_id=pending.request_id,
            session_id=pending.session_id,
            user_id=pending.user_id,
            agent_id=approval_meta.get("agent_id") or "",
            tenant_id=approval_meta.get("tenant_id") or "",
            source_id=approval_meta.get("source_id") or "",
            tool_name=pending.tool_name,
            result_summary=pending.result_summary,
            findings_count=pending.findings_count,
            tool_input=tool_input,
            approve_command=f"/approve {pending.request_id}",
            deny_command=f"/deny {pending.request_id}",
        )
    except Exception:
        logger.exception(
            "zhaohu cron approval pending notification failed: request_id=%s",
            pending.request_id,
        )


async def notify_cron_approval_result(
    workspace: Any,
    pending: PendingApproval,
    *,
    decision: ExternalApprovalDecision,
    source_channel: str,
) -> None:
    """Notify zhaohu about the submitted approval result."""
    channel_manager = getattr(workspace, "channel_manager", None)
    zhaohu = await _get_channel(channel_manager, ZHAOHU_CHANNEL)
    if zhaohu is None:
        return
    sender = getattr(zhaohu, "send_cron_approval_result", None)
    if sender is None:
        return

    try:
        await sender(
            request_id=pending.request_id,
            session_id=pending.session_id,
            user_id=pending.user_id,
            tool_name=pending.tool_name,
            decision=_status_for_decision(decision),
            source_channel=source_channel,
        )
    except Exception:
        logger.exception(
            "zhaohu cron approval result notification failed: request_id=%s",
            pending.request_id,
        )


async def submit_external_approval_decision(
    *,
    workspace: Any,
    pending: PendingApproval,
    decision: ExternalApprovalDecision,
    source_channel: str,
    source_user_id: str | None = None,
    source_message_id: str | None = None,
    source_id: str | None = None,
    user_name: str | None = None,
    bbk_id: str | None = None,
) -> ExternalApprovalSubmission:
    """Submit an external approval decision through the console runner."""
    if pending.status != "pending":
        return ExternalApprovalSubmission(
            request_id=pending.request_id,
            decision=decision,
            status=pending.status,
            session_id=pending.session_id,
            submitted=False,
        )

    channel_manager = getattr(workspace, "channel_manager", None)
    console_channel = await _get_channel(channel_manager, CONSOLE_CHANNEL)
    if console_channel is None:
        raise RuntimeError("console channel not found")

    chat = await workspace.chat_manager.get_or_create_chat(
        pending.session_id,
        pending.user_id or "external-approval",
        CONSOLE_CHANNEL,
        name=_command_for_decision(decision, pending.request_id),
        meta=(
            {"agent_id": workspace.agent_id}
            if getattr(workspace, "agent_id", None)
            else None
        ),
    )

    await _wait_until_run_idle(workspace.task_tracker, chat.id)

    payload = build_external_approval_payload(
        pending=pending,
        decision=decision,
        source_channel=source_channel,
        source_user_id=source_user_id,
        source_message_id=source_message_id,
        source_id=source_id,
        user_name=user_name,
        bbk_id=bbk_id,
    )
    _queue, is_new_run = await workspace.task_tracker.attach_or_start(
        chat.id,
        payload,
        console_channel.stream_one,
    )

    await notify_cron_approval_result(
        workspace,
        pending,
        decision=decision,
        source_channel=source_channel,
    )

    return ExternalApprovalSubmission(
        request_id=pending.request_id,
        decision=decision,
        status="submitted",
        session_id=pending.session_id,
        chat_id=chat.id,
        submitted=True,
        reconnect=True,
        is_new_run=is_new_run,
    )
