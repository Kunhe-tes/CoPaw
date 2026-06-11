# -*- coding: utf-8 -*-
"""环境变量管理 API。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...envs import load_envs, save_envs, delete_env_var
from ...envs.runtime import (
    mask_env_value,
    validate_env_mapping,
)
from ...config.context import (
    is_valid_identity_value,
    resolve_storage_tenant_id,
)
from ...config.utils import (
    get_tenant_storage_secrets_dir,
)

router = APIRouter(prefix="/envs", tags=["envs"])

MANAGER_ROLES = frozenset({"manager", "admin"})
TARGET_FIELD_NAMES = frozenset(
    {
        "tenant_id",
        "source_id",
        "target_tenant_id",
        "target_source_id",
    },
)
RESERVED_SCOPE_FIELD_ERROR = (
    "Reserved scope field is not allowed in PUT /envs body: "
)


def _get_tenant_envs_path(request: Request) -> Path:
    """Get tenant-specific envs.json path."""
    tenant_id = getattr(request.state, "tenant_id", None)
    source_id = getattr(request.state, "source_id", None)
    scope_id = getattr(request.state, "scope_id", None)
    storage_tenant_id = resolve_storage_tenant_id(
        tenant_id,
        source_id,
        scope_id=scope_id,
    )
    secrets_dir = get_tenant_storage_secrets_dir(storage_tenant_id)
    return secrets_dir / "envs.json"


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------


class EnvVar(BaseModel):
    """Single environment variable."""

    key: str = Field(..., description="Variable name")
    value: str = Field(..., description="Variable value")


class EnvPatchRequest(BaseModel):
    """增量更新 env 的请求体。"""

    values: Dict[str, str] = Field(default_factory=dict)
    preserve: List[str] = Field(default_factory=list)
    delete: List[str] = Field(default_factory=list)


class TargetEnvWriteRequest(BaseModel):
    """manager 写入目标 scope env 的请求体。"""

    target_tenant_id: str = Field(..., description="Target tenant ID")
    target_source_id: str = Field(..., description="Target source ID")
    values: Dict[str, str] = Field(default_factory=dict)


class TargetEnvAudit(BaseModel):
    """目标 scope 写入审计信息，禁止包含原始 env 值。"""

    actor: str
    target_tenant_id: str
    target_source_id: str
    keys: List[str]


class TargetEnvWriteResponse(BaseModel):
    """manager target env 写入响应。"""

    envs: List[EnvVar]
    audit: TargetEnvAudit


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get(
    "",
    response_model=List[EnvVar],
    summary="List all environment variables",
)
async def list_envs(request: Request) -> List[EnvVar]:
    """返回当前租户配置的原始 env 值。"""
    envs = load_envs(_get_tenant_envs_path(request))
    return _plain_env_list(envs)


@router.put(
    "",
    response_model=List[EnvVar],
    summary="Batch save environment variables",
    description="Replace all environment variables with "
    "the provided dict. Keys not present are removed.",
)
async def batch_save_envs(
    request: Request,
    body: Dict[str, str],
) -> List[EnvVar]:
    """Batch save – full replacement of all env vars for the tenant."""
    _reject_reserved_scope_fields_or_400(body)
    cleaned = _validate_envs_or_400(body)
    save_envs(cleaned, _get_tenant_envs_path(request))
    return _plain_env_list(cleaned)


@router.patch(
    "",
    response_model=List[EnvVar],
    summary="Update environment variables",
)
async def patch_envs(
    request: Request,
    body: EnvPatchRequest,
) -> List[EnvVar]:
    """增量合并当前 scope env，兼容旧客户端的 preserve 字段。"""
    envs_path = _get_tenant_envs_path(request)
    existing = load_envs(envs_path)
    cleaned_values = _validate_envs_or_400(body.values)
    for key in body.delete:
        _validate_key_or_400(key)

    updated = dict(existing)
    for key in body.delete:
        updated.pop(key, None)
    updated.update(cleaned_values)
    save_envs(updated, envs_path)
    return _plain_env_list(updated)


@router.delete(
    "/{key}",
    response_model=List[EnvVar],
    summary="Delete an environment variable",
)
async def delete_env(request: Request, key: str) -> List[EnvVar]:
    """Delete a single env var for the tenant."""
    envs_path = _get_tenant_envs_path(request)
    envs = load_envs(envs_path)
    if key not in envs:
        raise HTTPException(
            404,
            detail=f"Env var '{key}' not found",
        )
    envs = delete_env_var(key, envs_path)
    return _plain_env_list(envs)


@router.put(
    "/target",
    response_model=TargetEnvWriteResponse,
    summary="Manager write target-scope environment variables",
)
async def write_target_envs(
    request: Request,
    body: TargetEnvWriteRequest,
) -> TargetEnvWriteResponse:
    """manager/internal 调用显式写入目标 tenant/source scope。"""
    actor = _require_manager(request)
    _validate_identity_or_400("target_tenant_id", body.target_tenant_id)
    _validate_identity_or_400("target_source_id", body.target_source_id)
    storage_tenant_id = resolve_storage_tenant_id(
        body.target_tenant_id,
        body.target_source_id,
    )
    if storage_tenant_id is None:
        raise HTTPException(400, detail="Target storage tenant is required")
    cleaned = _validate_envs_or_400(body.values)
    save_envs(
        cleaned,
        get_tenant_storage_secrets_dir(storage_tenant_id) / "envs.json",
    )
    audit = TargetEnvAudit(
        actor=actor,
        target_tenant_id=body.target_tenant_id,
        target_source_id=body.target_source_id,
        keys=sorted(cleaned),
    )
    _append_target_env_audit(storage_tenant_id, audit)
    return TargetEnvWriteResponse(envs=_masked_env_list(cleaned), audit=audit)


def _masked_env_list(envs: dict[str, str]) -> List[EnvVar]:
    """构造不暴露原始值的 env 列表响应。"""
    return [
        EnvVar(key=k, value=mask_env_value(v)) for k, v in sorted(envs.items())
    ]


def _plain_env_list(envs: dict[str, str]) -> List[EnvVar]:
    """构造保留原始值的 env 列表响应。"""
    return [EnvVar(key=k, value=v) for k, v in sorted(envs.items())]


def _validate_key_or_400(key: str) -> str:
    """把 env key 校验错误转换为 HTTP 400。"""
    try:
        return validate_env_mapping({key: ""}).popitem()[0]
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


def _validate_envs_or_400(envs: Dict[str, str]) -> dict[str, str]:
    """把 env 字典校验错误转换为 HTTP 400。"""
    try:
        return validate_env_mapping(envs)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


def _reject_reserved_scope_fields_or_400(envs: Dict[str, str]) -> None:
    """拒绝普通 PUT /envs 请求体中的保留 scope 字段。"""
    reserved_keys = sorted(set(envs) & TARGET_FIELD_NAMES)
    if reserved_keys:
        raise HTTPException(
            status_code=400,
            detail=RESERVED_SCOPE_FIELD_ERROR + ", ".join(reserved_keys),
        )


def _require_manager(request: Request) -> str:
    """校验 manager 权限并返回审计主体。"""
    role = request.headers.get("X-User-Role", "").strip().lower()
    if role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Manager role required")
    return (
        getattr(request.state, "user", None)
        or request.headers.get("X-User-Id")
        or "unknown"
    )


def _validate_identity_or_400(field_name: str, value: str) -> None:
    """校验 target tenant/source 标识，防止路径穿越式身份值。"""
    if not is_valid_identity_value(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} format",
        )


def _append_target_env_audit(
    storage_tenant_id: str,
    audit: TargetEnvAudit,
) -> None:
    """追加不含原始 env 值的 target 写入审计记录。"""
    audit_path = (
        get_tenant_storage_secrets_dir(storage_tenant_id) / "envs.audit.jsonl"
    )
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(audit_path.parent, 0o700)
    except OSError:
        pass
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **audit.model_dump(mode="json"),
    }
    with open(audit_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        fh.write("\n")
    try:
        os.chmod(audit_path, 0o600)
    except OSError:
        pass
