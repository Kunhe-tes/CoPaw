# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...config.context import (
    resolve_runtime_tenant_id,
    resolve_scope_id,
    resolve_scope_preferred_tenant_id,
    resolve_storage_tenant_id,
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
BROADCAST_CRON_FALLBACK_WARNING = (
    "cron offset not applied: unsupported cron, using original schedule"
)
BROADCAST_ALREADY_EXISTS_WARNING = (
    "broadcast skipped: target tenant already has child job"
)
BROADCAST_ORIGINAL_MODEL_SLOT_META_KEY = "broadcast_original_model_slot"
BROADCAST_MODEL_SLOT_FALLBACK_REASON_META_KEY = (
    "broadcast_model_slot_fallback_reason"
)


class BroadcastTenantListResponse(BaseModel):
    tenant_ids: list[str] = Field(default_factory=list)


class CronBroadcastTarget(BaseModel):
    tenant_id: str
    tenant_name: str | None = None
    bbk_id: str | None = None


class CronBroadcastRequest(BaseModel):
    target_tenant_ids: list[str] = Field(default_factory=list)
    targets: list[CronBroadcastTarget] = Field(default_factory=list)


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


@dataclass(frozen=True)
class _BroadcastContext:
    """保存一次广播请求内所有目标租户共享的执行上下文。"""

    source_job: CronJobSpec
    offsets: list[int]
    multi_agent_manager: Any
    tenant_workspace_pool: Any | None
    agent_id: str
    source_id: str | None
    timezone_name: str
    target_identity_by_tenant: dict[str, dict[str, str | None]]


@dataclass(frozen=True)
class _BroadcastSchedule:
    """保存目标租户最终使用的 cron 表达式和偏移信息。"""

    cron: str
    timezone: str
    offset_minutes: int
    warning: str


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
    """确保定时任务租户字段跟随当前请求上下文。"""
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
    storage_tenant_id = resolve_storage_tenant_id(manager_tenant_id, None)
    ProviderManager.ensure_tenant_provider_storage(storage_tenant_id)
    return ProviderManager.get_instance(storage_tenant_id)


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


def _join_broadcast_warnings(*warnings: str) -> str:
    return "; ".join(item for item in warnings if item)


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


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
    tenant_name: str | None = None,
    bbk_id: str | None = None,
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
            "bbk_id": bbk_id,
            "source_id": source_id,
            "tenant_name": tenant_name,
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


async def _find_existing_broadcast_child_job(
    mgr: CronManager,
    source_job_id: str,
) -> CronJobSpec | None:
    for job in await mgr.list_jobs():
        if (job.meta or {}).get("broadcast_source_job_id") == source_job_id:
            return job
    return None


def _normalize_broadcast_targets(
    body: CronBroadcastRequest,
) -> tuple[list[str], dict[str, dict[str, str | None]]]:
    if body.targets:
        raw_targets = body.targets
    else:
        raw_targets = [
            CronBroadcastTarget(tenant_id=tenant_id)
            for tenant_id in body.target_tenant_ids
        ]

    normalized_tenants: list[str] = []
    identity_by_tenant: dict[str, dict[str, str | None]] = {}
    seen: set[str] = set()
    try:
        for target in raw_targets:
            tenant_id = _validate_target_tenant_id(target.tenant_id)
            if tenant_id in seen:
                continue
            seen.add(tenant_id)
            normalized_tenants.append(tenant_id)
            identity_by_tenant[tenant_id] = {
                "tenant_name": _optional_text(target.tenant_name),
                "bbk_id": _optional_text(target.bbk_id),
            }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return normalized_tenants, identity_by_tenant


def _get_broadcast_multi_agent_manager(request: Request):
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
    return multi_agent_manager


def _build_broadcast_context(
    request: Request,
    source_job: CronJobSpec,
    normalized_tenants: list[str],
    target_identity_by_tenant: dict[str, dict[str, str | None]],
) -> _BroadcastContext:
    source_id = _request_source_id(request)
    return _BroadcastContext(
        source_job=source_job,
        offsets=compute_broadcast_offsets(len(normalized_tenants)),
        multi_agent_manager=_get_broadcast_multi_agent_manager(request),
        tenant_workspace_pool=getattr(
            request.app.state,
            "tenant_workspace_pool",
            None,
        ),
        agent_id=_request_agent_id(request),
        source_id=source_id,
        timezone_name=source_job.schedule.timezone or "UTC",
        target_identity_by_tenant=target_identity_by_tenant,
    )


def _resolve_broadcast_schedule(
    source_job: CronJobSpec,
    timezone_name: str,
    offset: int,
) -> _BroadcastSchedule:
    shifted = shift_cron_expression(
        source_job.schedule.cron,
        timezone_name,
        offset_minutes=offset,
    )
    if shifted.error:
        return _BroadcastSchedule(
            cron=source_job.schedule.cron,
            timezone=timezone_name,
            offset_minutes=0,
            warning=BROADCAST_CRON_FALLBACK_WARNING,
        )
    return _BroadcastSchedule(
        cron=shifted.cron,
        timezone=shifted.timezone,
        offset_minutes=offset,
        warning="",
    )


async def _get_broadcast_target_cron_manager(
    context: _BroadcastContext,
    tenant_id: str,
) -> tuple[CronManager, str | None]:
    if context.tenant_workspace_pool is not None:
        await context.tenant_workspace_pool.ensure_bootstrap(
            tenant_id,
            source_id=context.source_id,
        )
    runtime_tenant_id = resolve_runtime_tenant_id(
        tenant_id,
        context.source_id,
    )
    workspace = await context.multi_agent_manager.get_agent(
        context.agent_id,
        tenant_id=runtime_tenant_id,
    )
    if workspace.cron_manager is None:
        raise RuntimeError("CronManager not initialized")
    return workspace.cron_manager, runtime_tenant_id


def _build_existing_broadcast_result(
    tenant_id: str,
    existing_child_job: CronJobSpec,
    notification_timezone: str,
) -> CronBroadcastTenantResult:
    existing_meta = existing_child_job.meta or {}
    return CronBroadcastTenantResult(
        tenant_id=tenant_id,
        success=True,
        job_id=existing_child_job.id,
        cron=existing_child_job.schedule.cron,
        timezone=existing_child_job.schedule.timezone,
        offset_minutes=int(
            existing_meta.get(
                "broadcast_offset_minutes",
                0,
            )
            or 0,
        ),
        notification_timezone=notification_timezone,
        warning=BROADCAST_ALREADY_EXISTS_WARNING,
    )


async def _create_broadcast_child_job(
    context: _BroadcastContext,
    tenant_id: str,
    target_cron_manager: CronManager,
    runtime_tenant_id: str | None,
    schedule: _BroadcastSchedule,
) -> CronBroadcastTenantResult:
    target_job_id = str(uuid.uuid4())
    model_slot, warning, model_slot_fallback_reason = (
        _resolve_broadcast_model_slot(
            runtime_tenant_id or "default",
            context.source_job,
        )
    )
    target_identity = context.target_identity_by_tenant.get(tenant_id, {})
    target_job = _build_broadcast_job(
        context.source_job,
        job_id=target_job_id,
        target_tenant_id=tenant_id,
        source_id=context.source_id,
        cron=schedule.cron,
        timezone_name=schedule.timezone,
        offset_minutes=schedule.offset_minutes,
        model_slot=model_slot,
        model_slot_fallback_reason=model_slot_fallback_reason,
        tenant_name=target_identity.get("tenant_name"),
        bbk_id=target_identity.get("bbk_id"),
    )
    await target_cron_manager.create_or_replace_job(target_job)
    saved = await target_cron_manager.get_job(target_job_id)
    result_job = saved or target_job
    return CronBroadcastTenantResult(
        tenant_id=tenant_id,
        success=True,
        job_id=target_job_id,
        cron=result_job.schedule.cron,
        timezone=result_job.schedule.timezone,
        offset_minutes=schedule.offset_minutes,
        notification_timezone=context.timezone_name,
        warning=_join_broadcast_warnings(
            warning,
            schedule.warning,
        ),
    )


async def _broadcast_to_tenant(
    context: _BroadcastContext,
    tenant_id: str,
    offset: int,
) -> CronBroadcastTenantResult:
    schedule = _resolve_broadcast_schedule(
        context.source_job,
        context.timezone_name,
        offset,
    )
    try:
        target_cron_manager, runtime_tenant_id = (
            await _get_broadcast_target_cron_manager(context, tenant_id)
        )
        existing_child_job = await _find_existing_broadcast_child_job(
            target_cron_manager,
            context.source_job.id,
        )
        if existing_child_job is not None:
            return _build_existing_broadcast_result(
                tenant_id,
                existing_child_job,
                context.timezone_name,
            )
        return await _create_broadcast_child_job(
            context,
            tenant_id,
            target_cron_manager,
            runtime_tenant_id,
            schedule,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return CronBroadcastTenantResult(
            tenant_id=tenant_id,
            success=False,
            cron=schedule.cron,
            timezone=schedule.timezone,
            offset_minutes=schedule.offset_minutes,
            notification_timezone=context.timezone_name,
            error=repr(exc),
            warning=schedule.warning,
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
    if not body.target_tenant_ids and not body.targets:
        raise HTTPException(
            status_code=400,
            detail="No target tenant IDs provided",
        )

    normalized_tenants, target_identity_by_tenant = _normalize_broadcast_targets(
        body,
    )
    context = _build_broadcast_context(
        request,
        source_job,
        normalized_tenants,
        target_identity_by_tenant,
    )
    results = [
        await _broadcast_to_tenant(context, tenant_id, offset)
        for tenant_id, offset in zip(normalized_tenants, context.offsets)
    ]
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
