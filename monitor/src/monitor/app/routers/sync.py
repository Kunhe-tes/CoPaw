# -*- coding: utf-8 -*-
"""Sync API router for cron job data.

Provides endpoints for SWE to sync job definitions and execution records.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..models.cron import (
    CronJobSyncRequest,
    ExecutionSyncRequest,
    SyncJobResponse,
    DeleteJobResponse,
    RecordExecutionResponse,
)
from ..services.cron import SyncService, get_sync_service
from ..services.cron.notification_service import (
    ClaimedCronNotification,
    CronNotificationService,
    get_cron_notification_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor/sync", tags=["sync"])


class ClaimNotificationsRequest(BaseModel):
    """领取待发送通知的请求。"""

    lock_owner: str = Field(..., min_length=1)
    now_utc: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)
    stale_lock_seconds: int = Field(default=600, ge=60, le=3600)
    source_ids: list[str] = Field(default_factory=list)


class MarkNotificationSentRequest(BaseModel):
    """标记通知已发送的请求。"""

    sent_at: datetime | None = None


class MarkNotificationFailedRequest(BaseModel):
    """标记通知发送失败的请求。"""

    error: str = ""
    max_attempts: int = Field(default=3, ge=1, le=10)


@router.post("/job", response_model=SyncJobResponse)
async def sync_job(
    request: CronJobSyncRequest,
    service: SyncService = Depends(get_sync_service),
) -> SyncJobResponse:
    """Sync a cron job definition from SWE.

    This endpoint is called by SWE after creating or updating a job.
    It upserts the job into Monitor database.

    Args:
        request: Job sync request
        service: Sync service

    Returns:
        Sync confirmation
    """
    try:
        success = await service.sync_job(request)
        if not success:
            raise HTTPException(status_code=500, detail="Sync failed")
        return SyncJobResponse(synced=True)
    except Exception as e:
        logger.error("Failed to sync job %s: %s", request.id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/job/{job_id}", response_model=DeleteJobResponse)
async def delete_job(
    job_id: str,
    service: SyncService = Depends(get_sync_service),
) -> DeleteJobResponse:
    """Soft delete a cron job.

    This endpoint is called by SWE after deleting a job.
    It marks the job as deleted in Monitor database.

    Args:
        job_id: Job ID to delete
        service: Sync service

    Returns:
        Delete confirmation
    """
    try:
        success = await service.delete_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        return DeleteJobResponse(deleted=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete job %s: %s", job_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execution", response_model=RecordExecutionResponse)
async def record_execution(
    request: ExecutionSyncRequest,
    service: SyncService = Depends(get_sync_service),
) -> RecordExecutionResponse:
    """Record an execution history entry.

    接口收到请求后立即返回 success，然后在后台异步处理数据库写入。
    这种设计确保 SWE 服务不会因 Monitor 数据库写入延迟而阻塞。

    Args:
        request: Execution sync request
        service: Sync service

    Returns:
        立即返回成功响应，execution_id 为 None（实际 ID 在后台写入后生成）
    """
    # 创建后台任务异步处理数据库写入
    asyncio.create_task(_background_record_execution(service, request))

    # 立即返回成功响应
    return RecordExecutionResponse(recorded=True, execution_id=None)


async def _background_record_execution(
    service: SyncService,
    request: ExecutionSyncRequest,
) -> None:
    """后台异步处理执行记录写入。

    Args:
        service: Sync service
        request: Execution sync request
    """
    try:
        execution_id = await service.record_execution(request)
        if execution_id:
            logger.info(
                "Background recorded execution: job_id=%s execution_id=%s status=%s",
                request.job_id,
                execution_id,
                request.status,
            )
        else:
            logger.warning(
                "Background record execution returned None: job_id=%s",
                request.job_id,
            )
    except Exception as e:
        logger.error(
            "Background record execution failed for job %s: %s",
            request.job_id,
            e,
            exc_info=True,
        )


@router.post(
    "/notifications/claim",
    response_model=list[ClaimedCronNotification],
)
async def claim_notifications(
    request: ClaimNotificationsRequest,
    service: CronNotificationService = Depends(get_cron_notification_service),
) -> list[ClaimedCronNotification]:
    """领取已到通知时间的执行记录。"""
    try:
        return await service.claim_due_notifications(
            lock_owner=request.lock_owner,
            now_utc=request.now_utc or datetime.now(timezone.utc),
            limit=request.limit,
            stale_lock_seconds=request.stale_lock_seconds,
            source_ids=request.source_ids,
        )
    except Exception as e:
        logger.error("Failed to claim cron notifications: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/{execution_id}/sent")
async def mark_notification_sent(
    execution_id: int,
    request: MarkNotificationSentRequest,
    service: CronNotificationService = Depends(get_cron_notification_service),
) -> dict:
    """标记通知发送成功。"""
    try:
        await service.mark_sent(
            execution_id=execution_id,
            sent_at=request.sent_at or datetime.now(timezone.utc),
        )
        return {"marked": True}
    except Exception as e:
        logger.error("Failed to mark notification sent: id=%s %s", execution_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/{execution_id}/failed")
async def mark_notification_failed(
    execution_id: int,
    request: MarkNotificationFailedRequest,
    service: CronNotificationService = Depends(get_cron_notification_service),
) -> dict:
    """标记通知发送失败。"""
    try:
        await service.mark_failed(
            execution_id=execution_id,
            error=request.error,
            max_attempts=request.max_attempts,
        )
        return {"marked": True}
    except Exception as e:
        logger.error("Failed to mark notification failed: id=%s %s", execution_id, e)
        raise HTTPException(status_code=500, detail=str(e))
