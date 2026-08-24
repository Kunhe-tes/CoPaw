# -*- coding: utf-8 -*-
"""Ordered query runtime assembly independent of ``AgentRunner``."""

from __future__ import annotations

from typing import Any

from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest

from ...providers.provider_manager import ProviderManager
from .query_contracts import (
    _QueryPreflight,
    _RuntimeStartResult,
    QueryRuntimeOwner,
)


async def prepare_query_runtime(
    owner: QueryRuntimeOwner,
    *,
    request: AgentRequest,
    msgs: list[Any],
    query: str | None,
    preflight: _QueryPreflight,
) -> _RuntimeStartResult:
    """Assemble provider, request resources, hooks, agent, and MCP clients."""
    manager = await ProviderManager.get_or_create_instance(owner.tenant_id)
    await manager.refresh_if_due()
    inputs = await owner._build_query_runtime_inputs(
        request=request,
        msgs=msgs,
        preflight=preflight,
    )
    mcp_clients: list[Any] = []
    try:
        resources, block_result = await owner._start_query_runtime_resources(
            request=request,
            msgs=msgs,
            inputs=inputs,
            mcp_clients=mcp_clients,
        )
        if block_result is not None:
            return block_result
        runtime = await owner._finalize_query_runtime(
            request=request,
            query=query,
            msgs=msgs,
            preflight=preflight,
            inputs=inputs,
            resources=resources,
            mcp_clients=mcp_clients,
        )
        return _RuntimeStartResult(runtime=runtime)
    except Exception:
        if mcp_clients:
            await owner._cleanup_query_runtime_mcp_clients(mcp_clients)
        raise
