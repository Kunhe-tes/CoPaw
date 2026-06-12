# -*- coding: utf-8 -*-
"""MyMCP 在 market 服务中的本地配置辅助函数。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from ..runtime.config_store import (
    AgentProfileConfig,
    load_agent_config,
    load_root_config,
    save_agent_config,
)
from ..runtime.context import resolve_effective_tenant_id, tenant_context


@dataclass(frozen=True)
class MyMCPRequestContext:
    """MyMCP 本地配置操作所需的请求上下文。"""

    user_id: str
    tenant_id: str
    source_id: str
    effective_tenant_id: str
    agent_id: str
    user_name: str = ""
    bbk_id: str = ""

    def __post_init__(self) -> None:
        if not self.user_name:
            object.__setattr__(self, "user_name", self.user_id)


def resolve_my_mcp_request_context(request: Request) -> MyMCPRequestContext:
    """从请求头解析 MyMCP 所需上下文。"""
    from urllib.parse import unquote

    swe_root = request.app.state.marketplace.swe_root

    user_id = request.headers.get("X-User-Id", "").strip()
    user_name = unquote(request.headers.get("X-User-Name", "") or user_id)
    tenant_id = request.headers.get("X-Tenant-Id", "").strip() or user_id
    source_id = request.headers.get("X-Source-Id", "").strip()
    agent_id = request.headers.get("X-Agent-Id", "").strip()
    bbk_id = request.headers.get("X-Bbk-Id", "").strip()

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="X-Tenant-Id header is required",
        )
    if not source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header is required",
        )
    effective_tenant_id = resolve_effective_tenant_id(tenant_id, source_id)
    root_config = load_root_config(swe_root, effective_tenant_id)
    resolved_agent_id = (
        agent_id or root_config.agents.active_agent or "default"
    )

    if resolved_agent_id not in root_config.agents.profiles:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{resolved_agent_id}' not found",
        )

    return MyMCPRequestContext(
        user_id=user_id,
        user_name=user_name,
        tenant_id=tenant_id,
        source_id=source_id,
        effective_tenant_id=effective_tenant_id,
        agent_id=resolved_agent_id,
        bbk_id=bbk_id,
    )


def load_agent_config_for_request(
    request: Request,
) -> tuple[MyMCPRequestContext, AgentProfileConfig]:
    """按请求上下文加载目标 agent 配置。"""

    context = resolve_my_mcp_request_context(request)
    swe_root = request.app.state.marketplace.swe_root
    with tenant_context(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        source_id=context.source_id,
    ):
        agent_config = load_agent_config(
            swe_root,
            context.effective_tenant_id,
            context.agent_id,
        )
    return context, agent_config


def save_agent_config_for_request(
    context: MyMCPRequestContext,
    agent_config: AgentProfileConfig,
    request: Request,
) -> None:
    """按请求上下文保存目标 agent 配置。"""
    swe_root = request.app.state.marketplace.swe_root

    with tenant_context(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        source_id=context.source_id,
    ):
        save_agent_config(
            swe_root,
            context.effective_tenant_id,
            context.agent_id,
            agent_config,
        )


def mark_request_state(request: Request, context: MyMCPRequestContext) -> None:
    """将解析后的上下文回填到 request.state，兼容旧逻辑。"""

    request.state.user_id = context.user_id
    request.state.tenant_id = context.tenant_id
    request.state.source_id = context.source_id
    request.state.agent_id = context.agent_id
