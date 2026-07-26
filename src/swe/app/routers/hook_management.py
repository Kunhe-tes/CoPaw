# -*- coding: utf-8 -*-
"""HTTP boundary for Default Agent Profile Hook management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Annotated

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from ...agents.hook_runtime.models import HookContext
from ...config.config import AgentProfileRef
from ...config.context import resolve_request_effective_tenant_id
from ...config.utils import get_tenant_config_path_strict, load_config
from ..hook_management import (
    HookAuditActor,
    HookConfigurationSnapshot,
    HookManagementConflict,
    HookManagementService,
    HookManagementValidationError,
    UploadFilePayload,
)
from ..utils import schedule_agent_reload

router = APIRouter(prefix="/hook-management", tags=["hook-management"])


class HookConfigurationResponse(BaseModel):
    hooks: dict[str, Any]
    revision: str


class HookConfigurationUpdate(BaseModel):
    hooks: dict[str, Any]


class HookManualTestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    confirm_real_execution: bool = Field(alias="confirmRealExecution")
    handler: dict[str, Any]
    context: HookContext


def _effective_tenant_id(request: Request) -> str | None:
    return resolve_request_effective_tenant_id(
        getattr(request.state, "tenant_id", None),
        getattr(request.state, "source_id", None),
        getattr(request.state, "scope_id", None),
    )


def _actor_for_request(request: Request) -> HookAuditActor:
    return HookAuditActor(
        user_id=getattr(request.state, "user_id", None),
        tenant_id=_effective_tenant_id(request),
    )


def _service_for_request(request: Request) -> HookManagementService:
    tenant_id = _effective_tenant_id(request)
    config = load_config(get_tenant_config_path_strict(tenant_id))
    profile: AgentProfileRef | None = config.agents.profiles.get("default")
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Default Agent Profile not found",
        )
    return HookManagementService(
        Path(profile.workspace_dir).expanduser(),
        tenant_id=tenant_id,
    )


def _configuration_response(
    snapshot: HookConfigurationSnapshot,
) -> HookConfigurationResponse:
    return HookConfigurationResponse(
        hooks=snapshot.hooks,
        revision=snapshot.revision,
    )


@router.get("/configuration", response_model=HookConfigurationResponse)
async def get_configuration(request: Request) -> HookConfigurationResponse:
    try:
        return _configuration_response(
            _service_for_request(request).get_configuration(),
        )
    except HookManagementValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/configuration", response_model=HookConfigurationResponse)
async def put_configuration(
    payload: HookConfigurationUpdate,
    request: Request,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> HookConfigurationResponse:
    try:
        snapshot = _service_for_request(request).save_configuration(
            hooks=payload.hooks,
            expected_revision=if_match,
            actor=_actor_for_request(request),
        )
    except HookManagementConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HookManagementValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    schedule_agent_reload(
        request,
        "default",
        tenant_id=_effective_tenant_id(request),
    )
    return _configuration_response(snapshot)


@router.get("/scripts")
async def list_scripts(request: Request) -> list[dict[str, Any]]:
    return _service_for_request(request).list_scripts()


@router.post("/scripts")
async def upload_scripts(
    request: Request,
    files: list[UploadFile] = File(...),
    overwrite: str = "[]",
) -> dict[str, Any]:
    try:
        overwrite_names = set(json.loads(overwrite))
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="invalid overwrite list",
        ) from exc
    if not all(isinstance(name, str) for name in overwrite_names):
        raise HTTPException(status_code=400, detail="invalid overwrite list")

    payloads = [
        UploadFilePayload(file.filename or "", await file.read())
        for file in files
    ]
    result = _service_for_request(request).upload_scripts(
        files=payloads,
        overwrite_names=overwrite_names,
        actor=_actor_for_request(request),
    )
    return {
        "accepted": result.accepted_names,
        "warned": list(result.warned),
        "failed": [failure.__dict__ for failure in result.failed],
    }


@router.post("/manual-test")
async def manual_test(
    payload: HookManualTestRequest,
    request: Request,
) -> dict[str, Any]:
    if not payload.confirm_real_execution:
        raise HTTPException(
            status_code=400,
            detail="confirmRealExecution must be true",
        )
    try:
        result = await _service_for_request(request).manual_test(
            handler=payload.handler,
            context=payload.context,
            actor=_actor_for_request(request),
        )
    except HookManagementValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "handler_result": result.handler_result.model_dump(mode="json"),
        "redacted_summary": result.redacted_summary,
    }
