# -*- coding: utf-8 -*-
"""MCP HTTP header 解析工具。"""

from __future__ import annotations

import os
from typing import Mapping
from urllib.parse import urlparse

from swe.envs.runtime import resolve_tenant_env_references_mapping
from swe.runtime_invocation_claims import (
    RUNTIME_CLAIM_HEADER_KEYS,
    build_runtime_claim_headers,
)

_RESERVED_SWE_HEADER_KEYS = RUNTIME_CLAIM_HEADER_KEYS
_MCP_MARKET_SANDBOX_HOST = "mcpmarket-sandbox.platform.cmbchina.cn"
_FRONTEND_AUTHORIZATION_HEADER_NAMES = frozenset(
    {"authorization", "x-header-authorization"},
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


def _is_mcp_market_sandbox_url(url: str | None) -> bool:
    if not url:
        return False
    return urlparse(url).hostname == _MCP_MARKET_SANDBOX_HOST


def _filter_passthrough_headers(
    passthrough_headers: Mapping[str, str] | None,
    *,
    url: str | None = None,
) -> dict[str, str] | None:
    if not passthrough_headers:
        return None
    if not _is_mcp_market_sandbox_url(url):
        return dict(passthrough_headers)
    return {
        key: value
        for key, value in passthrough_headers.items()
        if str(key).casefold() not in _FRONTEND_AUTHORIZATION_HEADER_NAMES
    }


def build_mcp_http_headers(
    headers: Mapping[str, str] | None,
    *,
    passthrough_headers: Mapping[str, str] | None = None,
    url: str | None = None,
    session_id: str | None = None,
    chat_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, str] | None:
    """Build final HTTP MCP headers with reserved Swe runtime headers."""
    merged_headers = dict(resolve_mcp_http_headers(headers) or {})
    filtered_passthrough_headers = _filter_passthrough_headers(
        passthrough_headers,
        url=url,
    )
    if filtered_passthrough_headers:
        merged_headers.update(filtered_passthrough_headers)

    merged_headers = build_runtime_claim_headers(
        merged_headers,
        include_aliases=True,
        session_id=session_id,
        chat_id=chat_id,
        trace_id=trace_id,
    )

    return merged_headers or None
