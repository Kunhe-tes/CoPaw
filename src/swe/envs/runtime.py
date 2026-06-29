# -*- coding: utf-8 -*-
"""租户运行时环境变量加载、校验与合并。"""

from __future__ import annotations

import os
import re
from typing import Mapping

from swe.config.context import (
    TenantContextError,
    canonicalize_scope_id,
    get_current_scope_id,
    get_current_source_id,
    get_current_tenant_id,
    resolve_scope_id,
)
from swe.config.utils import get_tenant_secrets_dir
from swe.env_defaults import (
    get_backend_owned_secret_env_keys,
    get_system_configuration_env_keys,
)
from swe.tracing.sanitizer import register_sensitive_values

from .store import load_envs

ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PROTECTED_RUNTIME_ENV_KEYS = frozenset(
    {
        "SWE_WORKING_DIR",
        "SWE_SECRET_DIR",
        "PATH",
        "HOME",
        "SHELL",
        "BASH_ENV",
        "ENV",
        "ZDOTDIR",
        "IFS",
        "CDPATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "SWE_STDIO_LAUNCHER_DROP_ENV_KEYS",
    },
)

_USER_TOOL_SUBPROCESS_ALLOWED_PROTECTED_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "SHELL",
    },
)

_USER_TOOL_SUBPROCESS_BOUNDARY_ENV_KEYS = (
    PROTECTED_RUNTIME_ENV_KEYS
    - _USER_TOOL_SUBPROCESS_ALLOWED_PROTECTED_ENV_KEYS
)

MASKED_ENV_VALUE = "********"

TENANT_ENV_REFERENCE_PATTERN = re.compile(
    r"\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}",
)


def validate_env_key(key: str) -> str:
    """校验 env key，并返回去除首尾空白后的名称。"""
    normalized = key.strip() if isinstance(key, str) else ""
    if not normalized:
        raise ValueError("Env key cannot be empty")
    if not ENV_NAME_PATTERN.fullmatch(normalized):
        raise ValueError(f"Invalid env key: {normalized}")
    if normalized in PROTECTED_RUNTIME_ENV_KEYS:
        raise ValueError(f"Protected env key is not allowed: {normalized}")
    return normalized


def validate_env_mapping(envs: Mapping[str, str]) -> dict[str, str]:
    """校验并标准化 API 写入的 env 字典。"""
    cleaned: dict[str, str] = {}
    for key, value in envs.items():
        normalized_key = validate_env_key(key)
        if not isinstance(value, str):
            raise ValueError(
                f"Env value for {normalized_key} must be a string",
            )
        cleaned[normalized_key] = value
    return cleaned


def mask_env_value(value: str) -> str:
    """返回 routine read 使用的安全占位值。"""
    return MASKED_ENV_VALUE if value else ""


def _resolve_runtime_scope_id(
    *,
    runtime_scope_id: str | None = None,
    tenant_id: str | None = None,
    source_id: str | None = None,
) -> str | None:
    """优先使用显式 scope，其次使用当前上下文解析 scope。"""
    if runtime_scope_id:
        return canonicalize_scope_id(runtime_scope_id)

    current_scope_id = get_current_scope_id()
    if current_scope_id:
        return canonicalize_scope_id(current_scope_id)

    effective_tenant_id = tenant_id or get_current_tenant_id()
    effective_source_id = source_id or get_current_source_id()
    if effective_tenant_id and not effective_source_id:
        try:
            return canonicalize_scope_id(effective_tenant_id)
        except ValueError:
            return None
    return resolve_scope_id(effective_tenant_id, effective_source_id)


def _filter_runtime_env(envs: Mapping[str, str]) -> dict[str, str]:
    """过滤 tenant 可控 env，避免覆盖隔离和解释器边界。"""
    return {
        key: str(value)
        for key, value in envs.items()
        if key not in PROTECTED_RUNTIME_ENV_KEYS
    }


def _scrub_user_tool_subprocess_env(
    envs: Mapping[str, str],
    *,
    preserve_boundary_keys: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """删除不应继承到用户工具子进程的后端环境变量。"""
    preserved_boundary_keys = (
        preserve_boundary_keys & _USER_TOOL_SUBPROCESS_BOUNDARY_ENV_KEYS
    )
    blocked_keys = (
        get_system_configuration_env_keys()
        | get_backend_owned_secret_env_keys()
        | _USER_TOOL_SUBPROCESS_BOUNDARY_ENV_KEYS
    ) - preserved_boundary_keys
    return {
        key: str(value)
        for key, value in envs.items()
        if key not in blocked_keys
    }


def load_tenant_runtime_env(
    *,
    runtime_scope_id: str | None = None,
    tenant_id: str | None = None,
    source_id: str | None = None,
    allow_missing_context: bool = True,
) -> dict[str, str]:
    """从当前或显式 runtime scope 的 `.secret/envs.json` 加载 env。"""
    scope_id = _resolve_runtime_scope_id(
        runtime_scope_id=runtime_scope_id,
        tenant_id=tenant_id,
        source_id=source_id,
    )
    if scope_id is None:
        if allow_missing_context:
            return {}
        raise TenantContextError("Runtime scope context is not available")

    envs_path = get_tenant_secrets_dir(scope_id) / "envs.json"
    return load_envs(envs_path)


def build_runtime_env(
    *,
    base_env: Mapping[str, str] | None = None,
    call_env: Mapping[str, str] | None = None,
    runtime_scope_id: str | None = None,
    tenant_id: str | None = None,
    source_id: str | None = None,
    allow_missing_context: bool = True,
    allow_protected_call_env: bool = False,
    preserve_boundary_env_keys: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """按 process < tenant < call-specific 的优先级构造子进程 env。"""
    env = dict(os.environ if base_env is None else base_env)
    tenant_env = load_tenant_runtime_env(
        runtime_scope_id=runtime_scope_id,
        tenant_id=tenant_id,
        source_id=source_id,
        allow_missing_context=allow_missing_context,
    )
    env.update(_filter_runtime_env(tenant_env))

    if call_env:
        call_mapping = dict(call_env)
        if not allow_protected_call_env:
            call_mapping = _filter_runtime_env(call_mapping)
        env.update({key: str(value) for key, value in call_mapping.items()})

    register_sensitive_values(tenant_env.values())
    return _scrub_user_tool_subprocess_env(
        env,
        preserve_boundary_keys=preserve_boundary_env_keys,
    )


def get_tenant_runtime_env_value(
    key: str,
    *,
    runtime_scope_id: str | None = None,
    tenant_id: str | None = None,
    source_id: str | None = None,
    default: str | None = None,
) -> str | None:
    """读取单个 runtime scope env 值，不回退到 process env。"""
    try:
        envs = load_tenant_runtime_env(
            runtime_scope_id=runtime_scope_id,
            tenant_id=tenant_id,
            source_id=source_id,
        )
    except (TenantContextError, ValueError):
        return default
    value = envs.get(key, default)
    return None if value is None else str(value)


def resolve_tenant_env_references(value: str) -> str:
    """解析 `${ENV:KEY}` 形式的显式 tenant env 引用。"""

    def _replace(match: re.Match[str]) -> str:
        env_value = get_tenant_runtime_env_value(match.group(1))
        if env_value is not None:
            register_sensitive_values([env_value])
        return match.group(0) if env_value is None else env_value

    resolved = TENANT_ENV_REFERENCE_PATTERN.sub(_replace, value)
    if resolved != value:
        register_sensitive_values([resolved])
    return resolved


def resolve_tenant_env_references_mapping(
    values: Mapping[str, str] | None,
) -> dict[str, str] | None:
    """解析字典值中的显式 tenant env 引用。"""
    if not values:
        return None
    return {
        key: resolve_tenant_env_references(value)
        for key, value in values.items()
    }
