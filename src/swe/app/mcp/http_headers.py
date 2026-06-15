# -*- coding: utf-8 -*-
"""MCP HTTP header 解析工具。"""

from __future__ import annotations

import os
from typing import Mapping

from swe.config.context import get_current_source_id, get_current_tenant_id
from swe.envs.runtime import resolve_tenant_env_references_mapping

_RESERVED_SWE_HEADER_KEYS = frozenset(
    {
        "x-swe-tenant-id",
        "x-swe-source-id",
        "x-swe-session-id",
        "x-swe-trace-id",
    },
)


def resolve_mcp_http_headers(
    headers: Mapping[str, str] | None,
) -> dict[str, str] | None:
    """先展开进程 env，再解析 tenant env 引用，避免 secret 被二次展开。"""
    if not headers:
        return None

    expanded_headers = {
        key: os.path.expandvars(value) for key, value in headers.items()
    }
    return resolve_tenant_env_references_mapping(expanded_headers)


def build_mcp_http_headers(
    headers: Mapping[str, str] | None,
    *,
    passthrough_headers: Mapping[str, str] | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, str] | None:
    """Build final HTTP MCP headers with reserved Swe runtime headers."""
    merged_headers = dict(resolve_mcp_http_headers(headers) or {})
    if passthrough_headers:
        merged_headers.update(passthrough_headers)

    merged_headers = {
        key: value
        for key, value in merged_headers.items()
        if key.lower() not in _RESERVED_SWE_HEADER_KEYS
    }

    tenant_id = get_current_tenant_id()
    source_id = get_current_source_id()
    if tenant_id:
        merged_headers["x-swe-tenant-id"] = tenant_id
    if source_id:
        merged_headers["x-swe-source-id"] = source_id
    if session_id:
        merged_headers["x-swe-session-id"] = session_id
    if trace_id:
        merged_headers["x-swe-trace-id"] = trace_id

    return merged_headers or None
