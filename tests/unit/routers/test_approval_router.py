# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.approvals.external import (
    ExternalApprovalDecision,
    ExternalApprovalSubmission,
)
from swe.app.routers import approvals as approvals_router


def test_external_approve_accepts_empty_body(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    workspace = SimpleNamespace()
    pending = SimpleNamespace(
        request_id="approval-1",
        session_id="cron-task:job-1",
        status="pending",
    )

    class _Service:
        async def get_request(self, request_id: str):
            captured["request_id"] = request_id
            return pending

    async def _get_agent_for_request(_request):
        return workspace

    async def _submit_external_approval_decision(**kwargs):
        captured.update(kwargs)
        return ExternalApprovalSubmission(
            request_id="approval-1",
            decision=ExternalApprovalDecision.APPROVE,
            status="submitted",
            session_id="cron-task:job-1",
            chat_id="chat-1",
            submitted=True,
            reconnect=True,
            is_new_run=True,
        )

    monkeypatch.setattr(
        approvals_router,
        "get_agent_for_request",
        _get_agent_for_request,
    )
    monkeypatch.setattr(
        approvals_router,
        "get_approval_service",
        _Service,
    )
    monkeypatch.setattr(
        approvals_router,
        "submit_external_approval_decision",
        _submit_external_approval_decision,
    )

    app = FastAPI()
    app.include_router(approvals_router.router)
    client = TestClient(app)

    response = client.post(
        "/approvals/approval-1/approve",
        headers={"X-Source-Id": "source-a"},
    )

    assert response.status_code == 200
    assert response.json()["reconnect"] is True
    assert captured["workspace"] is workspace
    assert captured["pending"] is pending
    assert captured["decision"] == ExternalApprovalDecision.APPROVE
    assert captured["source_channel"] == "zhaohu"
    assert captured["source_id"] == "source-a"


def test_get_approval_status_returns_external_submission(monkeypatch) -> None:
    class _Service:
        async def get_request_status(self, request_id: str, **_kwargs):
            assert request_id == "approval-1"
            return {
                "request_id": "approval-1",
                "status": "submitted",
                "session_id": "session-1",
                "decision": "approve",
                "source_channel": "zhaohu",
                "source_user_id": "approver-1",
                "source_message_id": "message-1",
                "submitted_at": 1.0,
            }

    monkeypatch.setattr(
        approvals_router,
        "get_approval_service",
        _Service,
    )

    app = FastAPI()
    app.include_router(approvals_router.router)
    client = TestClient(app)

    response = client.get("/approvals/approval-1/status")

    assert response.status_code == 200
    assert response.json() == {
        "request_id": "approval-1",
        "status": "submitted",
        "session_id": "session-1",
        "decision": "approve",
        "source_channel": "zhaohu",
        "source_user_id": "approver-1",
        "source_message_id": "message-1",
        "submitted_at": 1.0,
    }


def _router_client(monkeypatch, pending, submitted):
    workspace = SimpleNamespace()

    class _Service:
        async def get_request(self, request_id: str):
            return pending

    async def _get_agent_for_request(_request):
        return workspace

    async def _submit_external_approval_decision(**kwargs):
        submitted.append(kwargs)
        return ExternalApprovalSubmission(
            request_id=pending.request_id,
            decision=ExternalApprovalDecision.APPROVE,
            status="submitted",
            session_id=pending.session_id,
            chat_id="chat-1",
            submitted=True,
            reconnect=True,
            is_new_run=True,
        )

    monkeypatch.setattr(
        approvals_router,
        "get_agent_for_request",
        _get_agent_for_request,
    )
    monkeypatch.setattr(
        approvals_router,
        "get_approval_service",
        _Service,
    )
    monkeypatch.setattr(
        approvals_router,
        "submit_external_approval_decision",
        _submit_external_approval_decision,
    )
    app = FastAPI()
    app.include_router(approvals_router.router)
    return TestClient(app)


def test_external_approve_rejects_foreign_user(monkeypatch) -> None:
    """审批归属他人时不得提交决议。"""
    pending = SimpleNamespace(
        request_id="approval-1",
        session_id="session-1",
        status="pending",
        user_id="owner-1",
    )
    submitted: list[dict[str, Any]] = []
    client = _router_client(monkeypatch, pending, submitted)

    response = client.post(
        "/approvals/approval-1/approve",
        headers={"X-User-Id": "attacker-1"},
    )

    assert response.status_code == 403
    assert submitted == []


def test_external_approve_allows_owner(monkeypatch) -> None:
    """归属用户本人可以正常提交决议。"""
    pending = SimpleNamespace(
        request_id="approval-1",
        session_id="session-1",
        status="pending",
        user_id="owner-1",
    )
    submitted: list[dict[str, Any]] = []
    client = _router_client(monkeypatch, pending, submitted)

    response = client.post(
        "/approvals/approval-1/approve",
        headers={"X-User-Id": "owner-1"},
    )

    assert response.status_code == 200
    assert submitted[0]["caller_user_id"] == "owner-1"
