# -*- coding: utf-8 -*-
"""update_my_mcp 版本递增行为测试 (R2 / T7).

仅做 schema 与基础逻辑校验；完整端到端走 T12 e2e 测试。
"""

from __future__ import annotations

import pytest


def test_mymcp_detail_has_version_response_fields():
    """T7：MyMCPDetail 必须包含 version_changed / previous_version / bump_reason."""
    from market.app.routers.my_mcp import MyMCPDetail

    fields = MyMCPDetail.model_fields
    assert "version_changed" in fields
    assert "previous_version" in fields
    assert "bump_reason" in fields


def test_mymcp_update_request_accepts_version():
    """T7：MyMCPUpdateRequest 必须接受可选 version 字段."""
    from market.app.routers.my_mcp import MyMCPUpdateRequest

    fields = MyMCPUpdateRequest.model_fields
    assert "version" in fields
    # 不传 version 时为 None
    req = MyMCPUpdateRequest(description="x")
    assert req.version is None
    # 显式传 version
    req2 = MyMCPUpdateRequest(version="9.9.9")
    assert req2.version == "9.9.9"
