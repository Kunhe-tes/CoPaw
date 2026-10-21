# -*- coding: utf-8 -*-
"""解析当前租户实际使用的模型，只返回身份，不暴露凭据。"""

from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from ...providers.models import ModelSlotConfig
from .managed_api import _identity
from .managed_model_preparation import _available, get_model_manager

router = APIRouter(
    prefix="/internal/cron/managed",
    tags=["managed-cron-resources"],
)


class ModelResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_slot: ModelSlotConfig | None = None


@router.post("/resolve-model", summary="解析当前租户执行使用的实际模型")
async def resolve_managed_model(
    request: Request,
    body: ModelResolutionRequest,
):
    _, tenant, source, _ = _identity(request)
    manager = get_model_manager(
        SimpleNamespace(tenant_id=tenant, source_id=source),
    )
    slot = body.model_slot
    if not _available(manager, slot):
        slot = manager.get_active_model()
    if not _available(manager, slot):
        raise HTTPException(409, "cron_default_model_unavailable")
    return {"provider_id": slot.provider_id, "model": slot.model}
