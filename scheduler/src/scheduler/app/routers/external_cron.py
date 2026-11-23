# -*- coding: utf-8 -*-
"""新版用户任务的对外查询及批调度触发接口。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .managed_callbacks import scheduling_service
from .managed_cron import caller_identity
from .managed_cron_management import require_managed_runtime
from ..database import connection
from ..services.cron.managed.contracts import ManagedCronNotFound
from ..services.cron.managed.executions import ExecutionConflict
from ..services.cron.managed.external_query import ExternalManagedJobs
from ..services.cron.managed.identity import (
    CallerIdentity,
    encode_scope,
    identity_value,
)
from ..services.cron.managed.scheduling import (
    BatchAlreadyActive,
    ManagedSchedulingService,
)

router = APIRouter(prefix="/scheduler/external/cron", tags=["external-cron"])
logger = logging.getLogger(__name__)


class BatchRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(alias="jobId", description="新版批调度父任务 ID")

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, value):
        return identity_value(value)


def _identity(headers):
    """查询租户与viewer分离；不查SWE配置，不把viewer冒充为租户。"""
    tenant = identity_value(headers.get("x-tenant-id", ""))
    source = identity_value(headers.get("x-source-id", ""))
    agent = identity_value(headers.get("x-agent-id", "default"))
    viewer = headers.get("x-user-id") or None
    if viewer is not None:
        viewer = identity_value(viewer)
    scope = encode_scope(tenant, source)
    supplied = headers.get("x-scope-id")
    if supplied is not None and supplied not in {
        scope,
        f"scope.v1.{scope}",
        f"{tenant}-{source}",
    }:
        raise ValueError("conflicting_cron_scope")
    return tenant, source, agent, viewer


@router.get(
    "/jobs",
    response_model=list[dict],
    summary="对外查询新版定时任务列表",
)
async def list_external_jobs(request: Request):
    """按tenant/source/Agent读取未删除的Scheduler用户任务，返回完整数组。

    X-Tenant-Id、X-Source-Id必填；X-Agent-Id缺省为default，不解析SWE active Agent。
    X-User-Id可选且仅用于个人可见性。查询只允许日历缓存刷新，不写任务业务表或启动工作区。
    无匹配记录返回空数组；数据库不可用或关键状态缺失返回503，不回退旧文件或内存。
    """
    try:
        identity = _identity(request.headers)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    try:
        return await ExternalManagedJobs(connection.get_db_connection()).list(
            *identity,
        )
    except Exception as error:
        logger.warning(
            "external_cron_query_unavailable error_type=%s",
            type(error).__name__,
        )
        raise HTTPException(503, "cron_database_unavailable") from error


@router.post(
    "/batch/run",
    status_code=202,
    summary="对外受理新版整批手动执行",
    dependencies=[Depends(require_managed_runtime)],
)
async def run_external_batch(
    body: BatchRunRequest,
    caller: CallerIdentity = Depends(caller_identity),
    service: ManagedSchedulingService = Depends(scheduling_service),
):
    """沿用可信网关身份及任务归属，按父任务登记整批执行。"""
    try:
        result = await service.run_batch(caller, body.job_id)
    except ManagedCronNotFound as error:
        raise HTTPException(404, "cron_job_not_found") from error
    except BatchAlreadyActive as error:
        raise HTTPException(
            409,
            {"code": str(error), "batch_id": error.batch_id},
        ) from error
    except ExecutionConflict as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        logger.warning(
            "external_cron_batch_run_unavailable error_type=%s",
            type(error).__name__,
        )
        raise HTTPException(503, "cron_batch_run_unavailable") from error
    if not result["accepted"]:
        raise HTTPException(409, result["reason"])
    return result
