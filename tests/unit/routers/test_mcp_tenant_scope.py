# -*- coding: utf-8 -*-
"""MCP router scope resolution tests."""

from types import SimpleNamespace

from swe.app.routers import mcp as mcp_router
from swe.config.context import encode_scope_id
from swe.config.context import tenant_context


def test_mcp_router_prefers_request_scope_id_over_logical_tenant() -> None:
    """有显式 scope_id 时，MCP 路由必须使用该 runtime scope。"""
    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="tenant-a",
            source_id="ruice",
            scope_id=encode_scope_id("tenant-a", "ruice"),
        ),
    )

    resolved = mcp_router._request_effective_tenant_id(request)

    assert resolved == encode_scope_id("tenant-a", "ruice")


def test_mcp_router_scopes_non_default_tenant_with_source() -> None:
    """没有 scope_id 时，MCP 路由也必须对任意 tenant 做 source scope。"""
    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="tenant-a",
            source_id="ruice",
        ),
    )

    resolved = mcp_router._request_effective_tenant_id(request)

    assert resolved == encode_scope_id("tenant-a", "ruice")


def test_mcp_router_request_working_dir_uses_default_source_template() -> None:
    """default 用户访问 MCP 时应命中 default_{source} 目录。"""
    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="default",
            source_id="CMSJY",
            scope_id=encode_scope_id("default", "CMSJY"),
        ),
    )

    with tenant_context(
        tenant_id="default",
        source_id="CMSJY",
        scope_id=encode_scope_id("default", "CMSJY"),
    ):
        path = mcp_router._request_tenant_working_dir(request)

    assert path.name == "default_CMSJY"
