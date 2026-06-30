from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from swe.app.approvals.external import (
    ExternalApprovalDecision,
    notify_cron_approval_pending,
    submit_external_approval_decision,
)
from swe.app.approvals.service import ApprovalService
from swe.config.context import tenant_context
from swe.security.tool_guard.approval import ApprovalDecision


class _Result:
    findings: list[Any] = []
    findings_count = 0


class _ConsoleChannel:
    def resolve_session_id(self, sender_id: str, channel_meta: dict) -> str:
        return channel_meta.get("session_id") or f"console:{sender_id}"

    async def stream_one(self, payload):
        yield payload


class _ZhaohuChannel:
    def __init__(self) -> None:
        self.pending_calls: list[dict[str, Any]] = []
        self.result_calls: list[dict[str, Any]] = []

    async def send_cron_approval_card(self, **kwargs):
        self.pending_calls.append(kwargs)
        return (0, "noop")

    async def send_cron_approval_result(self, **kwargs):
        self.result_calls.append(kwargs)
        return (0, "noop")


class _ChannelManager:
    def __init__(self) -> None:
        self.console = _ConsoleChannel()
        self.zhaohu = _ZhaohuChannel()

    async def get_channel(self, name: str):
        if name == "console":
            return self.console
        if name == "zhaohu":
            return self.zhaohu
        return None


class _ChatManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get_or_create_chat(
        self,
        session_id: str,
        user_id: str,
        channel: str,
        name: str = "New Chat",
        meta: dict[str, Any] | None = None,
    ):
        self.calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "channel": channel,
                "name": name,
                "meta": meta,
            },
        )
        return SimpleNamespace(
            id=f"chat:{session_id}",
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            name=name,
            meta=meta or {},
        )


class _TaskTracker:
    def __init__(self, statuses: list[str] | None = None) -> None:
        self.statuses = list(statuses or ["idle"])
        self.attach_calls: list[dict[str, Any]] = []

    async def get_status(self, _run_key: str) -> str:
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    async def attach_or_start(self, run_key, payload, stream_fn):
        self.attach_calls.append(
            {
                "run_key": run_key,
                "payload": payload,
                "stream_fn": stream_fn,
            },
        )
        return asyncio.Queue(), True


class _Session:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.mutate_calls: list[dict[str, Any]] = []

    async def mutate_session_state(
        self,
        *,
        session_id: str,
        mutator,
        user_id: str = "",
        create_if_not_exist: bool = True,
        **_kwargs,
    ) -> dict[str, Any]:
        self.mutate_calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "create_if_not_exist": create_if_not_exist,
            },
        )
        result = mutator(self.state)
        if result is not None:
            self.state = result
        return self.state


def _workspace(task_tracker: _TaskTracker | None = None) -> SimpleNamespace:
    session = _Session()
    return SimpleNamespace(
        agent_id="agent-a",
        channel_manager=_ChannelManager(),
        chat_manager=_ChatManager(),
        task_tracker=task_tracker or _TaskTracker(),
        runner=SimpleNamespace(session=session),
        session=session,
    )


@pytest.mark.asyncio
async def test_external_approve_submits_console_approve_message() -> None:
    service = ApprovalService()
    workspace = _workspace()

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="execute_shell_command",
            result=_Result(),
            extra={
                "approval_kind": "tool_guard",
                "tool_call": {
                    "id": "tool-1",
                    "name": "execute_shell_command",
                    "input": {"cmd": "echo hi"},
                },
            },
        )

        result = await submit_external_approval_decision(
            workspace=workspace,
            pending=pending,
            decision=ExternalApprovalDecision.APPROVE,
            source_channel="zhaohu",
            source_user_id="zhaohu-user",
            source_id="source-a",
        )

    assert result.submitted is True
    assert result.reconnect is True
    assert result.chat_id == "chat:session-1"
    assert workspace.chat_manager.calls[0]["channel"] == "console"

    attach = workspace.task_tracker.attach_calls[0]
    payload = attach["payload"]
    assert attach["run_key"] == "chat:session-1"
    assert payload["channel_id"] == "console"
    assert payload["sender_id"] == "user-1"
    assert payload["content_parts"][0].text == f"/approve {pending.request_id}"
    assert payload["meta"]["session_id"] == "session-1"
    assert payload["meta"]["source_id"] == "source-a"
    assert payload["meta"]["approval_request_id"] == pending.request_id
    assert payload["meta"]["approval_source_channel"] == "zhaohu"

    memory_content = workspace.session.state["agent"]["memory"]["content"]
    assert memory_content[0][0]["role"] == "user"
    assert memory_content[0][0]["content"] == f"/approve {pending.request_id}"
    assert memory_content[0][0]["metadata"]["approval_request_id"] == (
        pending.request_id
    )
    assert memory_content[0][0]["metadata"]["approval_source_channel"] == (
        "zhaohu"
    )

    zhaohu = workspace.channel_manager.zhaohu
    assert zhaohu.result_calls[0]["decision"] == "approved"


@pytest.mark.asyncio
async def test_external_decision_does_not_resubmit_completed_approval() -> None:
    service = ApprovalService()
    workspace = _workspace()

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="cron-task:job-1",
            user_id="user-1",
            channel="console",
            tool_name="execute_shell_command",
            result=_Result(),
        )
        await service.resolve_request(
            pending.request_id,
            ApprovalDecision.APPROVED,
        )

        result = await submit_external_approval_decision(
            workspace=workspace,
            pending=pending,
            decision=ExternalApprovalDecision.DENY,
            source_channel="zhaohu",
        )

    assert result.submitted is False
    assert result.status == "approved"
    assert workspace.task_tracker.attach_calls == []
    assert workspace.channel_manager.zhaohu.result_calls == []


@pytest.mark.asyncio
async def test_pending_notification_applies_to_all_sessions() -> None:
    service = ApprovalService()
    workspace = _workspace()

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        cron_pending = await service.create_pending(
            session_id="cron-task:job-1",
            user_id="user-1",
            channel="console",
            tool_name="execute_shell_command",
            result=_Result(),
        )
        normal_pending = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="execute_shell_command",
            result=_Result(),
        )

        await notify_cron_approval_pending(
            cron_pending,
            channel_manager=workspace.channel_manager,
        )
        await notify_cron_approval_pending(
            normal_pending,
            channel_manager=workspace.channel_manager,
        )

    zhaohu = workspace.channel_manager.zhaohu
    assert len(zhaohu.pending_calls) == 2
    assert zhaohu.pending_calls[0]["request_id"] == cron_pending.request_id
    assert zhaohu.pending_calls[1]["request_id"] == normal_pending.request_id


@pytest.mark.asyncio
async def test_pending_notification_forwards_scope_metadata_from_extra() -> None:
    service = ApprovalService()
    workspace = _workspace()

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="execute_shell_command",
            result=_Result(),
            extra={
                "agent_id": "agent-a",
                "tenant_id": "tenant-a",
                "source_id": "source-a",
            },
        )

        await notify_cron_approval_pending(
            pending,
            channel_manager=workspace.channel_manager,
        )

    zhaohu = workspace.channel_manager.zhaohu
    assert zhaohu.pending_calls[0]["agent_id"] == "agent-a"
    assert zhaohu.pending_calls[0]["tenant_id"] == "tenant-a"
    assert zhaohu.pending_calls[0]["source_id"] == "source-a"
