# -*- coding: utf-8 -*-
"""校验 Daemon 审批命令的用户可见文案。"""

from __future__ import annotations

import pytest

from types import SimpleNamespace

from swe.app.approvals.service import ApprovalService
from swe.app.runner import daemon_commands
from swe.config.context import tenant_context


@pytest.mark.asyncio
async def test_daemon_approve_reports_missing_pending_in_chinese(
    monkeypatch,
) -> None:
    service = ApprovalService()
    monkeypatch.setattr(
        "swe.app.approvals.service._approval_service",
        service,
    )

    message = await daemon_commands.run_daemon_approve(
        daemon_commands.DaemonContext(),
        session_id="session-1",
    )

    assert message == (
        "**没有待审批请求**\n\n"
        "- 当前会话没有等待处理的工具审批。\n"
        "- 该命令仅在敏感工具调用等待你审核时有效。"
    )


def _result():
    return SimpleNamespace(findings=[], findings_count=0)


@pytest.mark.asyncio
async def test_daemon_approve_unknown_request_does_not_fall_back(
    monkeypatch,
) -> None:
    """指定了错误 ID 时不得回落批准 FIFO 队首。"""
    service = ApprovalService()
    monkeypatch.setattr(
        "swe.app.approvals.service._approval_service",
        service,
    )
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="execute_shell_command",
            result=_result(),
        )
        message = await daemon_commands.run_daemon_approve(
            daemon_commands.DaemonContext(),
            session_id="session-1",
            request_id="missing-request",
            user_id="user-1",
        )
    assert "审批请求不存在" in message
    assert pending.status == "pending"


@pytest.mark.asyncio
async def test_daemon_approve_filters_by_user(monkeypatch) -> None:
    """FIFO 批准只作用于调用方自己的请求。"""
    service = ApprovalService()
    monkeypatch.setattr(
        "swe.app.approvals.service._approval_service",
        service,
    )
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="execute_shell_command",
            result=_result(),
        )
        message = await daemon_commands.run_daemon_approve(
            daemon_commands.DaemonContext(),
            session_id="session-1",
            user_id="user-2",
        )
    assert "没有待审批请求" in message
    assert pending.status == "pending"


@pytest.mark.asyncio
async def test_daemon_approve_empty_identity_never_approves_owned(
    monkeypatch,
) -> None:
    """空身份必须严格匹配空 owner，不能批准有归属人的审批。"""
    service = ApprovalService()
    monkeypatch.setattr(
        "swe.app.approvals.service._approval_service",
        service,
    )
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        pending = await service.create_pending(
            session_id="session-1",
            user_id="victim",
            channel="console",
            tool_name="execute_shell_command",
            result=_result(),
        )
        by_id = await daemon_commands.run_daemon_approve(
            daemon_commands.DaemonContext(),
            session_id="session-1",
            request_id=pending.request_id,
            user_id="",
        )
        fifo = await daemon_commands.run_daemon_approve(
            daemon_commands.DaemonContext(),
            session_id="session-1",
            user_id="",
        )
    assert pending.status == "pending"
    assert "审批请求不存在" in by_id
    assert "没有待审批请求" in fifo
