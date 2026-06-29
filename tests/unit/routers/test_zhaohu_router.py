"""招乎回调路由审批卡片处理的回归测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from swe.app.approvals.external import ExternalApprovalDecision
from swe.app.routers import approvals as approvals_router
from swe.app.routers import zhaohu as zhaohu_router
from swe.config.context import encode_scope_id


@pytest.mark.asyncio
async def test_custom_card_approval_uses_addition_scope(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    async def _submit_decision(request_id, decision, approval_body, request):
        captured["request_id"] = request_id
        captured["decision"] = decision
        captured["approval_body"] = approval_body
        captured["request"] = request
        return SimpleNamespace(model_dump_json=lambda: '{"status":"ok"}')

    monkeypatch.setattr(
        approvals_router,
        "_submit_decision",
        _submit_decision,
    )

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/zhaohu/callback",
            "headers": [],
        },
    )
    body = zhaohu_router.ZhaohuCallbackRequest(
        msgId="msg-1",
        fromId="open-id",
        toId="robot-id",
        msgType="CustomCard",
        msgContent=json.dumps(
            {
                "addition": {
                    "request_id": "approval-1",
                    "type": "approve",
                    "agentId": "agent-a",
                    "tenant_id": "tenant-a",
                    "source_id": "source-a",
                },
            },
        ),
    )

    response = await zhaohu_router._handle_custom_card(request, body)

    assert response.status_code == 200
    assert request.state.agent_id == "agent-a"
    assert request.state.tenant_id == "tenant-a"
    assert request.state.user_id == "tenant-a"
    assert request.state.source_id == "source-a"
    assert request.state.scope_id == encode_scope_id("tenant-a", "source-a")
    assert request.state.effective_tenant_id == request.state.scope_id
    assert captured["request_id"] == "approval-1"
    assert captured["decision"] == ExternalApprovalDecision.APPROVE
    assert captured["request"] is request
    approval_body = captured["approval_body"]
    assert approval_body.source_channel == "zhaohu"
    assert approval_body.source_user_id == "tenant-a"
    assert approval_body.source_message_id == "approval-1"
