# -*- coding: utf-8 -*-
"""Agent-owned SubAgent expert configuration APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ...config.context import resolve_request_effective_tenant_id
from ...config.utils import get_tenant_config_path_strict, load_config
from ...app.subagents import (
    AgentOwnedDefinitionConflict,
    AgentOwnedDefinitionPackage,
    AgentOwnedDefinitionRepository,
    builtin_definition_provider,
)

router = APIRouter(prefix="/experts", tags=["experts"])


class ExpertPayload(BaseModel):
    """Managed fields accepted from the expert configuration form."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str
    instruction: str
    trigger_keywords: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    mcps: list[str] | None = None
    tools: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, str] | None = None
    budget: dict[str, int] = Field(default_factory=dict)


class ExpertResponse(BaseModel):
    definition_id: str
    revision: str
    valid: bool
    validation_error: str = ""
    enabled: bool = False
    definition: dict[str, Any] | None = None
    toml: str


def _effective_tenant_id(request: Request) -> str | None:
    return resolve_request_effective_tenant_id(
        getattr(request.state, "tenant_id", None),
        getattr(request.state, "source_id", None),
        getattr(request.state, "scope_id", None),
    )


def _repository(request: Request) -> AgentOwnedDefinitionRepository:
    tenant_id = _effective_tenant_id(request)
    agent_id = str(getattr(request.state, "agent_id", "") or "")
    if not agent_id:
        raise HTTPException(status_code=404, detail="Agent Profile not found")
    config = load_config(get_tenant_config_path_strict(tenant_id))
    profile = config.agents.profiles.get(agent_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Agent Profile not found")
    builtin_names = {
        definition.name
        for definition in builtin_definition_provider().list_definitions()
    }
    return AgentOwnedDefinitionRepository(
        Path(profile.workspace_dir).expanduser() / "agents",
        owner_scope=f"{tenant_id}/{agent_id}",
        builtin_names=builtin_names,
    )


def _response(package: AgentOwnedDefinitionPackage) -> ExpertResponse:
    definition = package.definition
    return ExpertResponse(
        definition_id=package.definition_id,
        revision=package.revision,
        valid=package.valid,
        validation_error=package.validation_error,
        enabled=definition.enabled if definition is not None else False,
        definition=(definition.model_dump(mode="json") if definition else None),
        toml=package.toml,
    )


def _conflict(exc: ValueError) -> HTTPException:
    status = 409 if isinstance(exc, AgentOwnedDefinitionConflict) else 422
    return HTTPException(status_code=status, detail=str(exc))


@router.get("", response_model=list[ExpertResponse])
async def list_experts(request: Request) -> list[ExpertResponse]:
    return [_response(package) for package in _repository(request).list()]


@router.get("/{definition_id}", response_model=ExpertResponse)
async def get_expert(definition_id: str, request: Request) -> ExpertResponse:
    try:
        package = _repository(request).get(definition_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if package is None:
        raise HTTPException(status_code=404, detail="expert not found")
    return _response(package)


@router.post("/preview", response_model=ExpertResponse)
async def preview_expert(
    payload: ExpertPayload,
    request: Request,
) -> ExpertResponse:
    try:
        return _response(_repository(request).preview(payload.model_dump()))
    except ValueError as exc:
        raise _conflict(exc) from exc


@router.post("", response_model=ExpertResponse, status_code=201)
async def create_expert(
    payload: ExpertPayload,
    request: Request,
) -> ExpertResponse:
    try:
        return _response(_repository(request).create(payload.model_dump()))
    except ValueError as exc:
        raise _conflict(exc) from exc


@router.put("/{definition_id}", response_model=ExpertResponse)
async def update_expert(
    definition_id: str,
    payload: ExpertPayload,
    request: Request,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ExpertResponse:
    try:
        package = _repository(request).update(
            definition_id,
            payload.model_dump(),
            expected_revision=if_match,
        )
    except ValueError as exc:
        raise _conflict(exc) from exc
    return _response(package)


@router.post("/{definition_id}/enable", response_model=ExpertResponse)
async def enable_expert(
    definition_id: str,
    request: Request,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ExpertResponse:
    try:
        package = _repository(request).enable(
            definition_id,
            expected_revision=if_match,
        )
    except ValueError as exc:
        raise _conflict(exc) from exc
    return _response(package)


@router.post("/{definition_id}/disable", response_model=ExpertResponse)
async def disable_expert(
    definition_id: str,
    request: Request,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ExpertResponse:
    try:
        package = _repository(request).disable(
            definition_id,
            expected_revision=if_match,
        )
    except ValueError as exc:
        raise _conflict(exc) from exc
    return _response(package)


@router.delete("/{definition_id}", status_code=204)
async def delete_expert(
    definition_id: str,
    request: Request,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> None:
    try:
        _repository(request).delete(definition_id, expected_revision=if_match)
    except ValueError as exc:
        raise _conflict(exc) from exc
