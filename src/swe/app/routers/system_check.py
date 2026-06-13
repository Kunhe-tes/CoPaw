# -*- coding: utf-8 -*-
"""Manager-only system self-check APIs."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...app.crons.auth_state import (
    CRON_AUTH_FILE_NAME,
    CronAuthState,
    ensure_utc,
    utc_now,
)
from ...config.context import is_valid_identity_value, resolve_scope_id
from ...config.utils import get_tenant_secrets_dir

router = APIRouter(prefix="/system-check", tags=["system-check"])

MANAGER_ROLES = frozenset({"manager", "admin"})
MAX_TENANT_BATCH_SIZE = 200

CronAuthExpiryStatus = Literal[
    "valid",
    "expired",
    "missing_file",
    "invalid_content",
    "unknown",
]


class CronAuthExpiryBatchRequest(BaseModel):
    """Batch request for cron auth expiry diagnostics."""

    source_id: str = Field(..., min_length=1, max_length=256)
    tenant_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_TENANT_BATCH_SIZE,
    )


class CronAuthExpiryResult(BaseModel):
    """Non-sensitive diagnostic result for one logical tenant."""

    tenant_id: str
    source_id: str
    status: CronAuthExpiryStatus
    is_expired: bool | None
    user_info_expires_at: str | None
    message: str


class CronAuthExpiryBatchResponse(BaseModel):
    """Batch response for cron auth expiry diagnostics."""

    results: list[CronAuthExpiryResult]


@router.post(
    "/cron-auth-expiry",
    response_model=CronAuthExpiryBatchResponse,
    summary="Manager batch cron auth expiry self-check",
)
async def check_cron_auth_expiry(
    request: Request,
    body: CronAuthExpiryBatchRequest,
) -> CronAuthExpiryBatchResponse:
    """Inspect source-scoped tenant cron auth expiry without exposing secrets."""
    _require_manager(request)
    source_id = _validate_identity_or_400("source_id", body.source_id)
    tenant_ids = _validate_tenant_ids_or_400(body.tenant_ids)

    return CronAuthExpiryBatchResponse(
        results=[
            _inspect_tenant_cron_auth(
                tenant_id=tenant_id,
                source_id=source_id,
            )
            for tenant_id in tenant_ids
        ],
    )


def _require_manager(request: Request) -> None:
    """Reject callers without manager/admin role."""
    role = request.headers.get("X-User-Role", "").strip().lower()
    if role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Manager role required")


def _validate_identity_or_400(field_name: str, value: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not is_valid_identity_value(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} format",
        )
    return normalized


def _validate_tenant_ids_or_400(tenant_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tenant_id in tenant_ids:
        tenant_id = _validate_identity_or_400("tenant_id", raw_tenant_id)
        if tenant_id in seen:
            raise HTTPException(
                status_code=400,
                detail=f"duplicate tenant_id: {tenant_id}",
            )
        seen.add(tenant_id)
        normalized.append(tenant_id)
    return normalized


def _inspect_tenant_cron_auth(
    *,
    tenant_id: str,
    source_id: str,
) -> CronAuthExpiryResult:
    scope_id = resolve_scope_id(tenant_id, source_id)
    if scope_id is None:
        return CronAuthExpiryResult(
            tenant_id=tenant_id,
            source_id=source_id,
            status="invalid_content",
            is_expired=None,
            user_info_expires_at=None,
            message="Runtime scope could not be resolved",
        )

    auth_path = get_tenant_secrets_dir(scope_id) / CRON_AUTH_FILE_NAME
    if not auth_path.is_file():
        return CronAuthExpiryResult(
            tenant_id=tenant_id,
            source_id=source_id,
            status="missing_file",
            is_expired=None,
            user_info_expires_at=None,
            message="No cron auth file was found",
        )

    try:
        with open(auth_path, "r", encoding="utf-8") as fh:
            raw_state = json.load(fh)
        state = CronAuthState.model_validate(raw_state)
        expires_at = ensure_utc(state.user_info_expires_at)
    except (OSError, ValueError, TypeError) as exc:
        _ = exc
        return CronAuthExpiryResult(
            tenant_id=tenant_id,
            source_id=source_id,
            status="invalid_content",
            is_expired=None,
            user_info_expires_at=None,
            message="Cron auth file content is invalid",
        )

    if expires_at is None:
        return CronAuthExpiryResult(
            tenant_id=tenant_id,
            source_id=source_id,
            status="unknown",
            is_expired=None,
            user_info_expires_at=None,
            message="Auth user info expiry cannot be determined",
        )

    is_expired = expires_at <= utc_now()
    return CronAuthExpiryResult(
        tenant_id=tenant_id,
        source_id=source_id,
        status="expired" if is_expired else "valid",
        is_expired=is_expired,
        user_info_expires_at=expires_at.isoformat(),
        message=(
            "Auth user info is expired"
            if is_expired
            else "Auth user info is valid"
        ),
    )
