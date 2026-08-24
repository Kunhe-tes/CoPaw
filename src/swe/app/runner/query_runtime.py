# -*- coding: utf-8 -*-
"""Ordered query runtime assembly independent of ``AgentRunner``."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest

from ...agents.hook_runtime.models import HookSessionOverlay
from ...agents.hook_runtime.models import HookSessionState
from ...agents.hook_runtime.skill_loader import (
    SkillHookLoadError,
    load_skill_hooks_for_session,
)
from ...constant import WORKING_DIR
from ...providers.provider_manager import ProviderManager
from ..source_system_config.runtime import get_system_prompt_injections
from .query_contracts import (
    _QueryPreflight,
    _QueryRuntime,
    _QueryRuntimeInputs,
    _QueryRuntimeResources,
    _RuntimeStartResult,
    QueryRuntimeOwner,
)

logger = logging.getLogger(__name__)


def build_runtime_mcp_clients(
    clients: list[Any],
    *,
    agent_config: Any,
    tenant_id: str | None,
    user_id: str,
    passthrough_headers: dict[str, str],
    session_id: str,
    chat_id: str | None,
    trace_id: str | None,
    frozen_tools_by_key: dict[str, list[dict[str, Any]]],
    build_lazy_clients: Any,
) -> None:
    """Attach this runtime's request-scoped lazy MCP clients."""
    clients.extend(
        build_lazy_clients(
            agent_config.mcp,
            tenant_id=tenant_id,
            user_id=user_id,
            passthrough_headers=passthrough_headers or None,
            session_id=session_id,
            chat_id=chat_id,
            trace_id=trace_id,
            frozen_tools_by_key=frozen_tools_by_key,
        ),
    )


async def select_runtime_context_directives(
    inputs: _QueryRuntimeInputs,
    request: AgentRequest,
    *,
    workspace_dir: Any,
    chat: Any,
    request_scenario_snapshot: Any,
    with_scenario_mcp: Any,
    request_context_references: Any,
    request_selected_skill_names: Any,
) -> Any:
    """Resolve scenario, reference, and explicit Skill directives for a chat."""
    from .context_references import build_context_reference_directives
    from .skill_selection import SkillUseDirective, build_skill_use_directives
    from ..scenario_preset.runtime import (
        scenario_snapshot_skill_directives,
        scenario_snapshot_skill_names,
    )

    scenario_snapshot = request_scenario_snapshot(request) if chat else None
    inputs.agent_config = with_scenario_mcp(
        inputs.agent_config,
        scenario_snapshot,
        workspace_dir=workspace_dir,
        chat_id=chat.id if chat else "",
    )
    reference_directives = await build_context_reference_directives(
        workspace_dir=workspace_dir,
        channel=inputs.channel,
        agent_config=inputs.agent_config,
        references=request_context_references(request),
    )
    reference_skill_names = {
        directive.name
        for directive in reference_directives
        if isinstance(directive, SkillUseDirective)
    }
    selected_directives = build_skill_use_directives(
        workspace_dir=workspace_dir,
        channel=inputs.channel,
        selected_skill_names=[
            name
            for name in [
                *request_selected_skill_names(request),
                *scenario_snapshot_skill_names(scenario_snapshot),
            ]
            if name not in reference_skill_names
        ],
    )
    if scenario_snapshot is not None and chat is not None:
        selected_directives.extend(
            scenario_snapshot_skill_directives(
                scenario_snapshot,
                workspace_dir=workspace_dir,
                chat_id=chat.id,
            ),
        )
    all_directives = [*selected_directives, *reference_directives]
    inputs.selected_skill_directives = [
        directive
        for directive in all_directives
        if isinstance(directive, SkillUseDirective)
    ]
    inputs.selected_context_directives = [
        directive.render() for directive in all_directives
    ]
    return scenario_snapshot


async def load_selected_skill_hooks(
    *,
    inputs: _QueryRuntimeInputs,
    workspace_dir: Any,
    tenant_id: str | None,
    approved_http_urls: set[str],
) -> HookSessionOverlay:
    """Load validated selected skill Hooks after the session-start phase."""
    del tenant_id
    state: HookSessionState = inputs.hook_overlay
    for directive in inputs.selected_skill_directives:
        try:
            state = load_skill_hooks_for_session(
                skill_name=directive.name,
                skill_root=directive.path.parent,
                workspace_dir=workspace_dir,
                session_state=state,
                approved_http_urls=approved_http_urls,
            )
        except SkillHookLoadError as exc:
            logger.warning(
                "Rejected hooks for explicitly selected skill '%s': %s",
                directive.name,
                exc,
            )
    return HookSessionOverlay.model_validate(
        state.model_dump(mode="json", by_alias=True),
    )


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


async def finalize_query_runtime(
    owner: Any,
    *,
    request: AgentRequest,
    query: str | None,
    msgs: list[Any],
    preflight: _QueryPreflight,
    inputs: _QueryRuntimeInputs,
    resources: _QueryRuntimeResources,
    mcp_clients: list[Any],
    get_last_user_text: Any,
    debug_log: Any,
) -> _QueryRuntime:
    """Create and initialize the Agent for one assembled query runtime."""
    agent_build_started_at = time.perf_counter()
    agent = owner._create_agent_for_query(
        agent_config=inputs.agent_config,
        env_context=resources.env_context,
        mcp_clients=mcp_clients,
        request=request,
        session_id=inputs.session_id,
        user_id=inputs.user_id,
        channel=inputs.channel,
        chat=resources.chat,
        turn_id=resources.turn_id,
        hook_overlay=inputs.hook_overlay,
        auth_token=inputs.auth_token,
        approved_tool_call=preflight.approved_tool_call,
        current_user_text=query or get_last_user_text(msgs) or "",
    )
    await agent.register_mcp_clients()
    agent.set_console_output_enabled(enabled=False)
    debug_log(
        "swe_agent_build_duration_ms=%d agent_id=%s tenant_id=%s "
        "mcp_client_count=%d",
        int((time.perf_counter() - agent_build_started_at) * 1000),
        owner.agent_id,
        owner.tenant_id,
        len(mcp_clients),
    )
    runtime = _QueryRuntime(
        agent=agent,
        agent_config=inputs.agent_config,
        tenant_hooks=inputs.tenant_hooks,
        hook_overlay=inputs.hook_overlay,
        chat=resources.chat,
        session_skill_detector=None,
        mcp_clients=mcp_clients,
        session_id=inputs.session_id,
        user_id=inputs.user_id,
        channel=inputs.channel,
        skip_history=inputs.skip_history,
        pending_confirmed_skill_snapshots={},
        selected_context_directives=inputs.selected_context_directives,
    )
    owner._attach_session_skill_detector(runtime=runtime, request=request)
    return runtime


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
