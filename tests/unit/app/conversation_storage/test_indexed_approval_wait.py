# -*- coding: utf-8 -*-
"""SQL 轮次结束时审批等待状态的判定测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swe.app.conversation_storage import runner_integration


def _service(record):
    class _Service:
        async def get_request(self, _request_id):
            return record

    return _Service()


@pytest.mark.asyncio
async def test_approval_wait_requires_pending_status(monkeypatch):
    monkeypatch.setattr(
        "swe.app.approvals.get_approval_service",
        lambda: _service(SimpleNamespace(status="pending")),
    )
    assert await runner_integration._approval_is_still_pending("id") is True

    for status in ("approved", "denied", "timeout", "superseded"):
        monkeypatch.setattr(
            "swe.app.approvals.get_approval_service",
            lambda status=status: _service(SimpleNamespace(status=status)),
        )
        assert (
            await runner_integration._approval_is_still_pending("id") is False
        )


@pytest.mark.asyncio
async def test_approval_wait_handles_missing_and_failures(monkeypatch):
    monkeypatch.setattr(
        "swe.app.approvals.get_approval_service",
        lambda: _service(None),
    )
    assert await runner_integration._approval_is_still_pending("id") is False
    assert await runner_integration._approval_is_still_pending(None) is False

    class _Broken:
        async def get_request(self, _request_id):
            raise RuntimeError("approval service unavailable")

    monkeypatch.setattr(
        "swe.app.approvals.get_approval_service",
        _Broken,
    )
    assert await runner_integration._approval_is_still_pending("id") is False
