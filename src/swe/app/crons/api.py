# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...config.context import (
    resolve_runtime_tenant_id,
    resolve_scope_id,
    resolve_scope_preferred_tenant_id,
)
from ...config.utils import list_logical_tenant_ids
from ...providers.provider_manager import ProviderManager
from .broadcast import compute_broadcast_offsets, shift_cron_expression
from .manager import CronManager
from .models import CronJobListItem, CronJobSpec, CronJobView

router = APIRouter(prefix="/cron", tags=["cron"])

BROADCAST_MODEL_SLOT_WARNING = (
    "model_slot not copied: provider/model unavailable in target tenant"
)
BROADCAST_ORIGINAL_MODEL_SLOT_META_KEY = "broadcast_original_model_slot"
BROADCAST_MODEL_SLOT_FALLBACK_REASON_META_KEY = (
    "broadcast_model_slot_fallback_reason"
)


class BroadcastTenantListResponse(BaseModel):
    tenant_ids: list[str] = Field(default_factory=list)


class CronBroadcastRequest(BaseModel):
    target_tenant_ids: list[str] = Field(default_factory=list)


class CronBroadcastTenantResult(BaseModel):
    tenant_id: str
    success: bool
    job_id: str = ""
    cron: str = ""
    timezone: str = ""
    offset_minutes: int = 0
    notification_timezone: str = ""
    error: str = ""
    warning: str = ""


class CronBroadcastResponse(BaseModel):
    results: list[CronBroadcastTenantResult] = Field(default_factory=list)


async def get_cron_manager(
    request: Request,
) -> CronManager:
    """Get cron manager for the active agent."""
    from ..agent_context import get_agent_for_request

    workspace = await get_agent_for_request(request)
    if workspace.cron_manager is None:
        raise HTTPException(
            status_code=500,
            detail="CronManager not initialized",
        )
    return workspace.cron_manager


def _inject_request_tenant(spec: CronJobSpec, request: Request) -> CronJobSpec:
    """Force cron job tenant_id, bbk_id, source_id, tenant_name to follow request context."""
    tenant_id = getattr(request.state, "tenant_id", None)
    bbk_id = getattr(request.state, "bbk_id", None)
    source_id = getattr(request.state, "source_id", None)
    scope_id = getattr(request.state, "scope_id", None)
    user_name = getattr(request.state, "user_name", None)
    return spec.model_copy(
        update={
            "tenant_id": tenant_id,
            "bbk_id": bbk_id,
            "source_id": source_id,
            "scope_id": scope_id,
            "tenant_name": user_name,
        },
    )


def _get_request_user_id(request: Request) -> str | None:
    state_user_id = getattr(request.state, "user_id", None)
    if state_user_id:
        return state_user_id
    return request.headers.get("X-User-Id")


def _inject_creator_user(
    spec: CronJobSpec,
    request: Request,
    existing: CronJobSpec | None = None,
) -> CronJobSpec:
    if spec.task_type not in {"agent", "text"}:
        return spec
    meta = dict(spec.meta or {})
    existing_creator = (
        (existing.meta or {}).get("creator_user_id") if existing else None
    )
    creator_user_id = (
        existing_creator
        or meta.get("creator_user_id")
        or _get_request_user_id(request)
    )
    if creator_user_id:
        meta["creator_user_id"] = creator_user_id
    return spec.model_copy(update={"meta": meta})


def _validate_cron_job_model_slot(
    request: Request,
    spec: CronJobSpec,
) -> None:
    if spec.task_type != "agent" or spec.model_slot is None:
        return
    tenant_id = resolve_scope_preferred_tenant_id(
        getattr(request.state, "tenant_id", None),
        getattr(request.state, "source_id", None),
        getattr(request.state, "scope_id", None),
    )
    manager_tenant_id = tenant_id or "default"
    manager = _get_provider_manager(manager_tenant_id)
    provider = manager.get_provider(spec.model_slot.provider_id)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=(f"Provider '{spec.model_slot.provider_id}' not found."),
        )
    if not provider.has_model(spec.model_slot.model):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Model '{spec.model_slot.model}' not found in provider "
                f"'{spec.model_slot.provider_id}'."
            ),
        )


def _get_provider_manager(manager_tenant_id: str):
    ProviderManager.ensure_tenant_provider_storage(manager_tenant_id)
    return ProviderManager.get_instance(manager_tenant_id)


def _resolve_broadcast_model_slot(
    runtime_tenant_id: str,
    source_job: CronJobSpec,
):
    if source_job.model_slot is None:
        return None, "", ""
    manager = _get_provider_manager(runtime_tenant_id)
    provider = manager.get_provider(source_job.model_slot.provider_id)
    if provider is None:
        return (
            None,
            BROADCAST_MODEL_SLOT_WARNING,
            "provider_not_found",
        )
    if not provider.has_model(source_job.model_slot.model):
        return (
            None,
            BROADCAST_MODEL_SLOT_WARNING,
            "model_not_found",
        )
    return source_job.model_slot, "", ""


async def _ensure_task_binding_for_read(
    spec: CronJobSpec,
    request: Request,
    mgr: CronManager,
) -> CronJobSpec:
    if spec.task_type not in {"agent", "text"}:
        return spec

    meta = dict(spec.meta or {})
    has_binding = bool(
        meta.get("task_chat_id") and meta.get("task_session_id"),
    )
    has_creator = bool(meta.get("creator_user_id"))
    if has_binding and has_creator:
        return spec

    rebound = _inject_creator_user(spec, request, existing=spec)
    await mgr.create_or_replace_job(rebound)
    saved = await mgr.get_job(spec.id)
    return saved or rebound


def _serialize_state(state):
    if hasattr(state, "model_dump"):
        return state.model_dump(mode="json")
    return state


def _request_source_id(request: Request) -> str | None:
    return getattr(request.state, "source_id", None)


def _request_agent_id(request: Request) -> str:
    return getattr(request.state, "agent_id", None) or "default"


def _validate_target_tenant_id(tenant_id: str) -> str:
    value = str(tenant_id or "").strip()
    if not value:
        raise ValueError("tenant_id is required")
    if len(value) > 256:
        raise ValueError(f"Invalid tenant ID format: {value}")
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"Invalid tenant ID format: {value}")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"Invalid tenant ID format: {value}")
    return value


def _build_broadcast_job(
    source_job: CronJobSpec,
    *,
    job_id: str,
    target_tenant_id: str,
    source_id: str | None,
    cron: str,
    timezone_name: str,
    offset_minutes: int,
    model_slot,
    model_slot_fallback_reason: str,
) -> CronJobSpec:
    meta = dict(source_job.meta or {})
    for key in (
        "task_chat_id",
        "task_session_id",
        "task_has_scheduled_result",
        "task_last_scheduled_preview",
        "task_unread_execution_count",
        "task_last_scheduled_run_at",
        "pause_reason",
        "auto_paused_at",
        "unread_count_at_pause",
        "external_job_id",
        BROADCAST_ORIGINAL_MODEL_SLOT_META_KEY,
        BROADCAST_MODEL_SLOT_FALLBACK_REASON_META_KEY,
    ):
        meta.pop(key, None)
    meta.update(
        {
            "creator_user_id": target_tenant_id,
            "broadcast_source_job_id": source_job.id,
            "broadcast_original_cron": source_job.schedule.cron,
            "broadcast_original_timezone": source_job.schedule.timezone,
            "broadcast_offset_minutes": offset_minutes,
            "broadcast_notification_policy": "original_schedule",
        },
    )
    if source_job.model_slot is not None and model_slot is None:
        meta[BROADCAST_ORIGINAL_MODEL_SLOT_META_KEY] = (
            source_job.model_slot.model_dump(mode="json")
        )
        meta[BROADCAST_MODEL_SLOT_FALLBACK_REASON_META_KEY] = (
            model_slot_fallback_reason
        )

    request_spec = source_job.request
    if request_spec is not None:
        request_spec = request_spec.model_copy(
            update={
                "user_id": target_tenant_id,
                "session_id": f"cron-task:{job_id}",
            },
        )

    dispatch = source_job.dispatch.model_copy(
        update={
            "target": source_job.dispatch.target.model_copy(
                update={
                    "user_id": target_tenant_id,
                    "session_id": f"cron-task:{job_id}",
                },
            ),
        },
    )

    return source_job.model_copy(
        update={
            "id": job_id,
            "enabled": True,
            "tenant_id": target_tenant_id,
            "bbk_id": None,
            "source_id": source_id,
            "tenant_name": None,
            "scope_id": resolve_scope_id(target_tenant_id, source_id),
            "schedule": source_job.schedule.model_copy(
                update={
                    "cron": cron,
                    "timezone": timezone_name,
                },
            ),
            "request": request_spec,
            "model_slot": model_slot,
            "dispatch": dispatch,
            "meta": meta,
        },
    )


@router.get("/jobs", response_model=list[CronJobListItem])
async def list_jobs(
    request: Request,
    mgr: CronManager = Depends(get_cron_manager),
):
    user_id = _get_request_user_id(request)
    jobs = [
        await _ensure_task_binding_for_read(job, request, mgr)
        for job in await mgr.list_jobs()
    ]
    # 实时刷新每个 job 的 next_run_at（原依赖 APScheduler，现按需计算）
    for job in jobs:
        await mgr.refresh_next_run_at(job)
    return [
        CronJobListItem(
            **job.model_dump(mode="json"),
            state=_serialize_state(mgr.get_state(job.id)),
            task=mgr.build_task_view(job, user_id),
        )
        for job in jobs
    ]


@router.get(
    "/broadcast/tenants",
    response_model=BroadcastTenantListResponse,
)
async def list_broadcast_tenants(
    request: Request,
) -> BroadcastTenantListResponse:
    """获取可广播定时任务的目标租户。"""
    return BroadcastTenantListResponse(
        tenant_ids=await list_logical_tenant_ids(
            _request_source_id(request),
            source_filter=True,
        ),
    )


@router.post(
    "/jobs/{job_id}/broadcast",
    response_model=CronBroadcastResponse,
)
async def broadcast_job(
    request: Request,
    job_id: str,
    body: CronBroadcastRequest,
    mgr: CronManager = Depends(get_cron_manager),
) -> CronBroadcastResponse:
    """将当前定时任务广播到多个租户。"""
    source_job = await mgr.get_job(job_id)
    if not source_job:
        raise HTTPException(status_code=404, detail="job not found")
    if not body.target_tenant_ids:
        raise HTTPException(
            status_code=400,
            detail="No target tenant IDs provided",
        )

    normalized_tenants = []
    try:
        for tenant_id in body.target_tenant_ids:
            normalized = _validate_target_tenant_id(tenant_id)
            if normalized not in normalized_tenants:
                normalized_tenants.append(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    offsets = compute_broadcast_offsets(len(normalized_tenants))
    multi_agent_manager = getattr(
        request.app.state,
        "multi_agent_manager",
        None,
    )
    if multi_agent_manager is None:
        raise HTTPException(
            status_code=500,
            detail="multi_agent_manager missing",
        )
    tenant_workspace_pool = getattr(
        request.app.state,
        "tenant_workspace_pool",
        None,
    )

    results: list[CronBroadcastTenantResult] = []
    agent_id = _request_agent_id(request)
    source_id = _request_source_id(request)
    timezone_name = source_job.schedule.timezone or "UTC"
    for tenant_id, offset in zip(normalized_tenants, offsets):
        shifted = shift_cron_expression(
            source_job.schedule.cron,
            timezone_name,
            offset_minutes=offset,
        )
        if shifted.error:
            results.append(
                CronBroadcastTenantResult(
                    tenant_id=tenant_id,
                    success=False,
                    timezone=shifted.timezone,
                    offset_minutes=offset,
                    notification_timezone=timezone_name,
                    error=shifted.error,
                ),
            )
            continue
        try:
            if tenant_workspace_pool is not None:
                await tenant_workspace_pool.ensure_bootstrap(
                    tenant_id,
                    source_id=source_id,
                )
            runtime_tenant_id = resolve_runtime_tenant_id(
                tenant_id,
                source_id,
            )
            workspace = await multi_agent_manager.get_agent(
                agent_id,
                tenant_id=runtime_tenant_id,
            )
            if workspace.cron_manager is None:
                raise RuntimeError("CronManager not initialized")
            target_job_id = str(uuid.uuid4())
            model_slot, warning, model_slot_fallback_reason = (
                _resolve_broadcast_model_slot(
                    runtime_tenant_id or "default",
                    source_job,
                )
            )
            target_job = _build_broadcast_job(
                source_job,
                job_id=target_job_id,
                target_tenant_id=tenant_id,
                source_id=source_id,
                cron=shifted.cron,
                timezone_name=shifted.timezone,
                offset_minutes=offset,
                model_slot=model_slot,
                model_slot_fallback_reason=model_slot_fallback_reason,
            )
            await workspace.cron_manager.create_or_replace_job(target_job)
            saved = await workspace.cron_manager.get_job(target_job_id)
            results.append(
                CronBroadcastTenantResult(
                    tenant_id=tenant_id,
                    success=True,
                    job_id=target_job_id,
                    cron=(saved or target_job).schedule.cron,
                    timezone=(saved or target_job).schedule.timezone,
                    offset_minutes=offset,
                    notification_timezone=timezone_name,
                    warning=warning,
                ),
            )
        except Exception as exc:  # pylint: disable=broad-except
            results.append(
                CronBroadcastTenantResult(
                    tenant_id=tenant_id,
                    success=False,
                    cron=shifted.cron,
                    timezone=shifted.timezone,
                    offset_minutes=offset,
                    notification_timezone=timezone_name,
                    error=repr(exc),
                ),
            )
    return CronBroadcastResponse(results=results)


@router.get("/jobs/{job_id}", response_model=CronJobView)
async def get_job(
    request: Request,
    job_id: str,
    mgr: CronManager = Depends(get_cron_manager),
):
    job = await mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job = await _ensure_task_binding_for_read(job, request, mgr)
    await mgr.refresh_next_run_at(job)
    return CronJobView(
        spec=job,
        state=_serialize_state(mgr.get_state(job_id)),
        task=mgr.build_task_view(job, _get_request_user_id(request)),
    )


@router.post("/jobs", response_model=CronJobSpec)
async def create_job(
    request: Request,
    spec: CronJobSpec,
    mgr: CronManager = Depends(get_cron_manager),
):
    # server generates id; ignore client-provided spec.id
    job_id = str(uuid.uuid4())
    created = spec.model_copy(update={"id": job_id})
    created = _inject_request_tenant(created, request)
    created = _inject_creator_user(created, request)
    _validate_cron_job_model_slot(request, created)
    await mgr.create_or_replace_job(created)
    saved = await mgr.get_job(job_id)
    return saved or created


@router.put("/jobs/{job_id}", response_model=CronJobSpec)
async def replace_job(
    request: Request,
    job_id: str,
    spec: CronJobSpec,
    mgr: CronManager = Depends(get_cron_manager),
):
    if spec.id != job_id:
        raise HTTPException(status_code=400, detail="job_id mismatch")
    existing = await mgr.get_job(job_id)
    spec = _inject_request_tenant(spec, request)
    spec = _inject_creator_user(spec, request, existing=existing)
    _validate_cron_job_model_slot(request, spec)
    await mgr.create_or_replace_job(spec)
    saved = await mgr.get_job(job_id)
    return saved or spec


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    mgr: CronManager = Depends(get_cron_manager),
):
    ok = await mgr.delete_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"deleted": True}


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, mgr: CronManager = Depends(get_cron_manager)):
    ok = await mgr.pause_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"paused": True}


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    mgr: CronManager = Depends(get_cron_manager),
):
    ok = await mgr.resume_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"resumed": True}


@router.post("/jobs/{job_id}/run")
async def run_job(job_id: str, mgr: CronManager = Depends(get_cron_manager)):
    try:
        await mgr.run_job(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="job not found") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    # Note: run_job is a manual execution, not a schedule mutation
    # No reload signal needed
    return {"started": True}


@router.get("/jobs/{job_id}/state")
async def get_job_state(
    job_id: str,
    mgr: CronManager = Depends(get_cron_manager),
):
    job = await mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return mgr.get_state(job_id).model_dump(mode="json")


@router.post("/jobs/{job_id}/task/mark-read")
async def mark_task_read(
    request: Request,
    job_id: str,
    mgr: CronManager = Depends(get_cron_manager),
):
    user_id = _get_request_user_id(request)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing")
    ok = await mgr.mark_task_read(job_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="task job not found")
    return {"marked_read": True}
