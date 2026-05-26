# -*- coding: utf-8 -*-
"""环境变量持久化与运行时加载入口。"""

from __future__ import annotations

from typing import Any

from .store import (
    delete_env_var,
    load_envs,
    load_envs_into_environ,
    save_envs,
    set_env_var,
)

_RUNTIME_EXPORTS = {
    "build_runtime_env",
    "get_tenant_runtime_env_value",
    "load_tenant_runtime_env",
    "mask_env_value",
    "resolve_tenant_env_references",
    "validate_env_key",
    "validate_env_mapping",
}

__all__ = [
    "build_runtime_env",
    "delete_env_var",
    "get_tenant_runtime_env_value",
    "load_envs",
    "load_envs_into_environ",
    "load_tenant_runtime_env",
    "mask_env_value",
    "resolve_tenant_env_references",
    "save_envs",
    "set_env_var",
    "validate_env_key",
    "validate_env_mapping",
]


def __getattr__(name: str) -> Any:
    """按需加载运行时 helpers，避免 bootstrap 阶段提前导入常量。"""
    if name not in _RUNTIME_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import runtime

    value = getattr(runtime, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """返回包含懒加载导出的模块属性列表。"""
    return sorted(set(globals()) | set(__all__))
