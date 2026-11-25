# -*- coding: utf-8 -*-
"""Approval service persistence contracts on an isolated MySQL schema."""

from types import SimpleNamespace
import asyncio

import pytest

from swe.app.approvals.service import ApprovalService
from swe.app.approvals.store import ApprovalAuditStore
from swe.config.context import tenant_context
from swe.security.tool_guard.approval import ApprovalDecision


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "replay_decision"),
    [
        (ApprovalDecision.APPROVED, ApprovalDecision.DENIED),
        (ApprovalDecision.DENIED, ApprovalDecision.APPROVED),
        (ApprovalDecision.TIMEOUT, ApprovalDecision.APPROVED),
    ],
)
async def test_approval_resolution_replay_persists_only_first_decision(
    conversation_test_database,
    decision,
    replay_decision,
):
    db = conversation_test_database
    audit_store = ApprovalAuditStore(db)
    await audit_store.initialize()
    service = ApprovalService()
    service.set_store(audit_store)

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="session-a",
            user_id="user-a",
            channel="console",
            tool_name="execute_shell_command",
            result=SimpleNamespace(findings=[], findings_count=1),
            extra={
                "agent_id": "agent-a",
                "tenant_id": "tenant-a",
                "source_id": "source-a",
                "approval_kind": "tool_guard",
                "tool_call": {
                    "id": "tool-call-a",
                    "name": "execute_shell_command",
                    "input": {"cmd": "echo safe"},
                },
            },
        )
        first = await service.resolve_request(pending.request_id, decision)
        replay = await service.resolve_request(
            pending.request_id,
            replay_decision,
        )

    request = await db.fetch_one(
        "SELECT status,scope_id,tenant_id,source_id "
        "FROM swe_tool_approval_requests WHERE request_id=%s",
        (pending.request_id,),
    )
    events = await db.fetch_all(
        "SELECT event_type,status,details_json FROM swe_tool_approval_events "
        "WHERE request_id=%s ORDER BY event_id",
        (pending.request_id,),
    )
    resolved = [event for event in events if event["event_type"] == "resolved"]

    assert first is pending
    assert replay is pending
    assert request["status"] == decision.value
    assert request["scope_id"] == pending.scope_id
    assert request["tenant_id"] == "tenant-a"
    assert request["source_id"] == "source-a"
    assert pending.future.result() is decision
    assert [event["event_type"] for event in events] == ["created", "resolved"]
    assert len(resolved) == 1
    assert resolved[0]["status"] == decision.value


@pytest.mark.asyncio
async def test_resolution_replay_repairs_audit_event_after_transient_write_failure(
    conversation_test_database,
    monkeypatch,
):
    from swe.app.runner.runner import AgentRunner

    db = conversation_test_database
    audit_store = ApprovalAuditStore(db)
    await audit_store.initialize()
    service = ApprovalService()

    class FailFirstResolvedEvent:
        failed = False

        async def upsert_request(self, *args, **kwargs):
            await audit_store.upsert_request(*args, **kwargs)

        async def add_event(self, pending, event_type, **kwargs):
            if event_type == "resolved" and not self.failed:
                self.failed = True
                raise OSError("transient resolved-event write failure")
            await audit_store.add_event(pending, event_type, **kwargs)

    flaky_store = FailFirstResolvedEvent()
    service.set_store(flaky_store)
    monkeypatch.setattr("swe.app.approvals.service._approval_service", service)
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="session-a",
            user_id="user-a",
            channel="console",
            tool_name="execute_shell_command",
            result=SimpleNamespace(findings=[], findings_count=1),
            extra={
                "agent_id": "agent-a",
                "tenant_id": "tenant-a",
                "source_id": "source-a",
            },
        )
        (
            first,
            consumed,
            tool_call,
        ) = await AgentRunner()._resolve_pending_approval(
            "session-a",
            f"/deny {pending.request_id}",
        )
        (
            replay,
            replay_consumed,
            replay_tool,
        ) = await AgentRunner()._resolve_pending_approval(
            "session-a",
            f"/approve {pending.request_id}",
        )

    events = await db.fetch_all(
        "SELECT event_type,status FROM swe_tool_approval_events "
        "WHERE request_id=%s ORDER BY event_id",
        (pending.request_id,),
    )
    request = await db.fetch_one(
        "SELECT status FROM swe_tool_approval_requests WHERE request_id=%s",
        (pending.request_id,),
    )
    assert first is not None and consumed and tool_call is None
    assert replay is not None and replay_consumed and replay_tool is None
    assert request["status"] == "denied"
    assert [(event["event_type"], event["status"]) for event in events] == [
        ("created", "pending"),
        ("resolved", "denied"),
    ]


@pytest.mark.asyncio
async def test_concurrent_resolution_persists_one_resolved_audit_event(
    conversation_test_database,
):
    db = conversation_test_database
    audit_store = ApprovalAuditStore(db)
    await audit_store.initialize()
    service = ApprovalService()
    service.set_store(audit_store)
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="session-a",
            user_id="user-a",
            channel="console",
            tool_name="execute_shell_command",
            result=SimpleNamespace(findings=[], findings_count=1),
        )
        results = await asyncio.gather(
            service.resolve_request_once(
                pending.request_id,
                ApprovalDecision.APPROVED,
            ),
            service.resolve_request_once(
                pending.request_id,
                ApprovalDecision.DENIED,
            ),
        )
    rows = await db.fetch_all(
        "SELECT event_type,status FROM swe_tool_approval_events "
        "WHERE request_id=%s ORDER BY event_id",
        (pending.request_id,),
    )
    resolved = [row for row in rows if row["event_type"] == "resolved"]
    assert sum(changed for _, changed in results) == 1
    assert len(resolved) == 1
    assert resolved[0]["status"] == pending.status
