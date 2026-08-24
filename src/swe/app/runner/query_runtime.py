# -*- coding: utf-8 -*-
"""Ordered query runtime assembly independent of ``AgentRunner``."""

from __future__ import annotations

import json
import logging
from typing import Any

from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest

from ...agents.hook_runtime.models import HookSessionOverlay
from ...constant import WORKING_DIR
from ...providers.provider_manager import ProviderManager
from ..source_system_config.runtime import get_system_prompt_injections
from .query_contracts import (
    _QueryPreflight,
    _QueryRuntimeInputs,
    _RuntimeStartResult,
    QueryRuntimeOwner,
)

logger = logging.getLogger(__name__)


async def build_query_runtime_inputs(
    owner: Any,
    *,
    request: AgentRequest,
    msgs: list[Any],
    preflight: _QueryPreflight,
    build_environment_context: Any,
    request_source_id: Any,
    request_user_name: Any,
    request_passthrough_headers: Any,
    with_hook_context: Any,
    merge_system_prompt_injections: Any,
    with_system_prompt_injections: Any,
    request_system_prompt_injections: Any,
    load_tenant_hooks: Any,
    load_agent_configuration: Any,
    current_passthrough_headers: Any,
) -> _QueryRuntimeInputs:
    """Resolve request values before connecting query runtime resources."""
    session_id = request.session_id
    user_id = request.user_id
    channel = getattr(request, "channel", "console")
    skip_history = getattr(request, "skip_history", False)
    logger.info(
        "Handle agent query:\n%s",
        json.dumps(
            {
                "session_id": session_id,
                "user_id": user_id,
                "channel": channel,
                "msgs_len": len(msgs) if msgs else 0,
                "msgs_str": str(msgs)[:300] + "...",
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    env_context = with_hook_context(
        build_environment_context(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            working_dir=str(owner.workspace_dir or WORKING_DIR),
            source_id=request_source_id(request),
            user_name=request_user_name(request),
        ),
        preflight.hook_additional_context,
    )
    agent_config = (
        preflight.agent_config
        if preflight.agent_config is not None
        else load_agent_configuration(
            owner.agent_id,
            tenant_id=owner.tenant_id,
        )
    )
    passthrough_headers = dict[str, str](
        current_passthrough_headers() or {},
    )
    passthrough_headers.update(request_passthrough_headers(request))
    cookie_header = getattr(request, "cookie", None)
    if cookie_header:
        passthrough_headers["cookie"] = cookie_header
    return _QueryRuntimeInputs(
        session_id=session_id,
        user_id=user_id,
        channel=channel,
        skip_history=skip_history,
        agent_config=agent_config,
        tenant_hooks=(
            preflight.tenant_hooks
            if preflight.tenant_hooks is not None
            else load_tenant_hooks(owner.tenant_id)
        ),
        hook_overlay=(
            preflight.hook_overlay
            if preflight.hook_overlay is not None
            else HookSessionOverlay()
        ),
        env_context=with_system_prompt_injections(
            env_context,
            merge_system_prompt_injections(
                get_system_prompt_injections(),
                request_system_prompt_injections(request),
            ),
        ),
        selected_context_directives=[],
        selected_skill_directives=[],
        auth_token=getattr(request, "auth_token", None),
        passthrough_headers=passthrough_headers,
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
