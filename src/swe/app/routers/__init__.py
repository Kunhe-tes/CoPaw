# -*- coding: utf-8 -*-
"""API routers 包级懒加载入口。"""

from __future__ import annotations

from importlib import import_module

from fastapi import APIRouter

_ROUTER_MODULES = (
    (".agents", "router"),
    (".agent", "router"),
    (".config", "router"),
    (".console", "router"),
    ("..crons.api", "router"),
    (".local_models", "router"),
    (".mcp", "router"),
    (".messages", "router"),
    (".providers", "router"),
    (".providers", "tenant_providers_router"),
    ("..runner.api", "router"),
    (".skills", "router"),
    (".skills_stream", "router"),
    (".tools", "router"),
    (".workspace", "router"),
    (".envs", "router"),
    (".token_usage", "router"),
    (".tracing", "router"),
    (".auth", "router"),
    (".files", "router"),
    (".settings", "router"),
    ("..instance", "instance_router"),
    ("..backup.router", "router"),
    ("..backup.batch_router", "router"),
    ("..backup.shell_router", "router"),
    (".zhaohu", "zhaohu_router"),
    ("..greeting", "greeting_router"),
    ("..featured_case", "featured_case_router"),
    ("..feedback", "router"),
    ("..html_preview_clicks", "router"),
    (".dream_logs", "router"),
    (".user_info", "router"),
    (".internal", "router"),
    (".internal", "public_router"),
    ("..source_system_config", "router"),
)

_MODULE_EXPORTS = {
    "agent",
    "agents",
    "auth",
    "config",
    "console",
    "dream_logs",
    "envs",
    "files",
    "internal",
    "local_models",
    "mcp",
    "messages",
    "providers",
    "settings",
    "skills",
    "skills_stream",
    "token_usage",
    "tools",
    "tracing",
    "user_info",
    "workspace",
    "zhaohu",
}

_ROUTER_CACHE: APIRouter | None = None


def _build_router() -> APIRouter:
    """按需构造聚合 API router。"""
    router = APIRouter()
    for module_path, attr_name in _ROUTER_MODULES:
        module = import_module(module_path, __name__)
        router.include_router(getattr(module, attr_name))
    return router


def create_agent_scoped_router() -> APIRouter:
    """Create agent-scoped router that wraps existing routers."""
    from .agent_scoped import create_agent_scoped_router as _create

    return _create()


def __getattr__(name: str):
    """按需导出聚合 router 或具体子模块。"""
    global _ROUTER_CACHE  # pylint: disable=global-statement

    if name == "router":
        if _ROUTER_CACHE is None:
            _ROUTER_CACHE = _build_router()
        return _ROUTER_CACHE

    if name in _MODULE_EXPORTS:
        return import_module(f".{name}", __name__)

    raise AttributeError(name)


__all__ = ["router", "create_agent_scoped_router", *_MODULE_EXPORTS]
