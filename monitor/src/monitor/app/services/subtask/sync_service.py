# -*- coding: utf-8 -*-
"""Subtask sync service for external API calls and status updates.

Provides methods for:
- Syncing subtask status from external API
- Computing execution async_status from subtask statuses
"""

import logging
from datetime import datetime
from typing import Optional, Tuple

import httpx

from ....config.constant import (
    ASYNC_TASK_QUERY_URL,
    ASYNC_TASK_APP_KEY,
    ASYNC_TASK_ENV_TAG,
    ASYNC_TASK_API_KEY,
    ASYNC_TASK_TIMEOUT_HOUR,
)
from .query_service import QueryService, get_query_service
from ...models.subtask import (
    SubtaskModel,
    SubtaskSyncStatusResponse,
    SubtaskSyncDetailItem,
    ExecutionAsyncStatusResponse,
)

logger = logging.getLogger(__name__)

# 外部 API 超时
API_TIMEOUT = 10.0

# 每批处理数量
BATCH_SIZE = 50

# 有效状态值
VALID_SUBTASK_STATUSES = ("SUC", "FAIL", "PART_SUC")


class SyncService:
    """Service for syncing subtask status from external API."""

    def __init__(self, query_service: Optional[QueryService] = None):
        """Initialize sync service.

        Args:
            query_service: Query service for database operations
        """
        self.query_service = query_service or get_query_service()
        self._client: Optional[httpx.AsyncClient] = None

    def _is_configured(self) -> bool:
        """Check if external API is configured."""
        return bool(
            ASYNC_TASK_QUERY_URL
            and ASYNC_TASK_APP_KEY
            and ASYNC_TASK_ENV_TAG
            and ASYNC_TASK_API_KEY,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=API_TIMEOUT)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_api_url(self, task_id: str) -> str:
        """Build external API URL for task status query."""
        return (
            f"{ASYNC_TASK_QUERY_URL}/app/{ASYNC_TASK_APP_KEY}"
            f"/tag/{ASYNC_TASK_ENV_TAG}/result/query/{task_id}"
        )

    def _parse_api_response(
        self,
        data: dict,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Parse API response and extract status.

        Args:
            data: API response JSON

        Returns:
            Tuple of (status, error_message)
        """
        return_code = data.get("returnCode", "")
        if return_code != "SUC0000":
            return None, f"returnCode={return_code}"

        body = data.get("body", [])
        if not body:
            return None, "No body"

        status = body.get("status", "")
        if status not in VALID_SUBTASK_STATUSES:
            return None, f"Invalid status={status}"

        return status, None

    async def _query_task_status(
        self,
        client: httpx.AsyncClient,
        task_id: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Query task status from external API.

        Args:
            client: HTTP client
            task_id: Subtask task_id

        Returns:
            Tuple of (status, error_message)
        """
        url = self._build_api_url(task_id)

        try:
            api_response = await client.post(
                url,
                headers={
                    "Content-type": "application/json;charset=utf-8",
                    "API-Key": ASYNC_TASK_API_KEY,
                },
                json={},
            )

            if api_response.status_code != 200:
                return None, f"API returned {api_response.status_code}"

            return self._parse_api_response(api_response.json())

        except httpx.TimeoutException:
            return None, "API timeout"
        except httpx.RequestError as e:
            return None, str(e)
        except Exception as e:
            logger.error(
                "Unexpected error querying task %s: %s",
                task_id[:20],
                e,
            )
            return None, str(e)

    def _check_pending_timeout(
        self,
        subtask: SubtaskModel,
        now: datetime,
    ) -> bool:
        """Check if pending subtask exceeds 24 hours.

        Args:
            subtask: Subtask to check
            now: Current datetime

        Returns:
            True if exceeds 24 hours, False otherwise
        """
        if not subtask.created_at:
            return False
        hours_pending = (now - subtask.created_at).total_seconds() / 3600
        return hours_pending > 24

    async def _process_pending_subtask(
        self,
        client: httpx.AsyncClient,
        subtask: SubtaskModel,
        now: datetime,
    ) -> SubtaskSyncDetailItem:
        """Process subtask with NULL/empty status.

        Args:
            client: HTTP client
            subtask: Subtask to process
            now: Current datetime

        Returns:
            SubtaskSyncDetailItem with processing result
        """
        detail = SubtaskSyncDetailItem(
            task_id=subtask.task_id,
            old_status=subtask.status,
        )

        # 兜底检查：超过24小时的pending子任务
        if self._check_pending_timeout(subtask, now):
            hours_pending = int(
                (now - subtask.created_at).total_seconds() / 3600,
            )
            logger.warning(
                "Subtask pending over 24h, marking TIMEOUT: task_id=%s hours=%d",
                subtask.task_id[:20],
                hours_pending,
            )
            await self.query_service.update_subtask_status(
                subtask.task_id,
                subtask.trace_id,
                "TIMEOUT",
            )
            detail.new_status = "TIMEOUT"
            detail.error = "Pending over 24h, fallback TIMEOUT"
            return detail

        if not self._is_configured():
            detail.error = "API not configured"
            return detail

        status, error = await self._query_task_status(
            client,
            subtask.task_id,
        )
        if status:
            await self.query_service.update_subtask_status(
                subtask.task_id,
                subtask.trace_id,
                status,
            )
            detail.new_status = status
            logger.info(
                "Synced subtask status: task_id=%s status=%s",
                subtask.task_id[:20],
                status,
            )
        else:
            detail.error = error or "Unknown error"
            logger.warning(
                "Failed to query task %s: %s",
                subtask.task_id[:20],
                detail.error,
            )
        return detail

    async def _process_non_pending_subtask(
        self,
        client: httpx.AsyncClient,
        subtask: SubtaskModel,
        is_timeout: bool,
    ) -> SubtaskSyncDetailItem:
        """Process subtask with FAIL/PART_SUC/TIMEOUT status.

        Args:
            client: HTTP client
            subtask: Subtask to process
            is_timeout: Whether current time exceeds timeout threshold

        Returns:
            SubtaskSyncDetailItem with processing result
        """
        detail = SubtaskSyncDetailItem(
            task_id=subtask.task_id,
            old_status=subtask.status,
        )

        if is_timeout:
            detail.error = "Timeout, skip update for non-pending status"
            logger.debug(
                "Skip update for subtask %s (status=%s, timeout mode)",
                subtask.task_id[:20],
                subtask.status,
            )
            return detail

        if not self._is_configured():
            detail.error = "API not configured"
            return detail

        status, error = await self._query_task_status(
            client,
            subtask.task_id,
        )
        if status and status != subtask.status:
            await self.query_service.update_subtask_status(
                subtask.task_id,
                subtask.trace_id,
                status,
            )
            detail.new_status = status
            logger.info(
                "Updated subtask status: task_id=%s old=%s new=%s",
                subtask.task_id[:20],
                subtask.status,
                status,
            )
        else:
            detail.error = error or "Status unchanged"
            logger.debug(
                "Subtask status unchanged: task_id=%s status=%s",
                subtask.task_id[:20],
                subtask.status,
            )
        return detail

    async def sync_subtask_status(
        self,
        batch_size: int = BATCH_SIZE,
    ) -> SubtaskSyncStatusResponse:
        """Sync subtask statuses from external API.

        查询范围：
        1. 所有无状态的子任务（不限制时间）
        2. 当天创建的 FAIL/PART_SUC/TIMEOUT 状态子任务

        处理逻辑：
        - NULL/空: 始终查询API并更新，超过24小时查询失败则标记TIMEOUT
        - FAIL/PART_SUC/TIMEOUT: 超时→跳过，未超时→查询有变化才更新
        """
        now = datetime.now()
        timeout_hour = ASYNC_TASK_TIMEOUT_HOUR
        is_timeout = now.hour >= timeout_hour

        logger.info(
            "Starting subtask sync: time=%s timeout_hour=%d is_timeout=%s",
            now.strftime("%H:%M"),
            timeout_hour,
            is_timeout,
        )

        subtasks = await self.query_service.get_today_pending_subtasks(
            limit=batch_size,
        )
        if not subtasks:
            logger.debug("No subtasks to sync")
            return SubtaskSyncStatusResponse(
                success=True,
                total_scanned=0,
                total_updated=0,
                total_failed=0,
            )

        response = SubtaskSyncStatusResponse(
            success=True,
            total_scanned=len(subtasks),
        )

        client = await self._get_client()

        for subtask in subtasks:
            # 原状态为 NULL/空：始终查询API并更新
            if subtask.status is None or subtask.status == "":
                detail = await self._process_pending_subtask(
                    client,
                    subtask,
                    now,
                )
            else:
                # 原状态为 FAIL/PART_SUC/TIMEOUT
                detail = await self._process_non_pending_subtask(
                    client,
                    subtask,
                    is_timeout,
                )

            response.details.append(detail)
            if detail.new_status:
                response.total_updated += 1
            else:
                response.total_failed += 1

        return response

    async def sync_execution_async_status(
        self,
        batch_size: int = 100,
    ) -> ExecutionAsyncStatusResponse:
        """Sync execution async_status from subtask statuses.

        根据时间阈值分类处理：
        - 无subtasks → success
        - 超时模式：全有状态才聚合，有pending跳过
        - 正常模式：全SUC→success，否则跳过
        """
        now = datetime.now()
        timeout_hour = ASYNC_TASK_TIMEOUT_HOUR
        is_timeout = now.hour >= timeout_hour

        logger.info(
            "Starting execution async_status sync: time=%s timeout_hour=%d is_timeout=%s",
            now.strftime("%H:%M"),
            timeout_hour,
            is_timeout,
        )

        executions = await self.query_service.get_pending_executions(
            limit=batch_size,
        )
        if not executions:
            logger.debug("No pending executions to sync")
            return ExecutionAsyncStatusResponse(
                success=True,
                total_scanned=0,
                total_updated=0,
            )

        response = ExecutionAsyncStatusResponse(
            success=True,
            total_scanned=len(executions),
        )

        for execution in executions:
            trace_id = execution.get("trace_id", "")
            execution_id: int = execution.get("id") or 0

            if execution_id == 0:
                logger.warning("Execution has no id")
                continue

            if not trace_id:
                logger.warning(
                    "Execution has no trace_id: id=%s",
                    execution_id,
                )
                # 无trace_id，标记success
                await self.query_service.update_execution_async_status(
                    execution_id,
                    "success",
                )
                response.total_updated += 1
                response.total_success += 1
                continue

            subtasks = await self.query_service.get_subtasks_by_trace_id(
                trace_id,
            )

            # 没有 subtasks，标记 success
            if not subtasks:
                await self.query_service.update_execution_async_status(
                    execution_id,
                    "success",
                )
                response.total_updated += 1
                response.total_success += 1
                logger.info(
                    "No subtasks, marked execution as success: id=%s",
                    execution_id,
                )
                continue

            if is_timeout:
                # 超时模式
                # 检查是否有无状态子任务
                has_pending = any(
                    s.status is None or s.status == "" for s in subtasks
                )
                if has_pending:
                    # 存在无状态子任务，不更新
                    logger.debug(
                        "Execution has pending subtasks, skip: id=%s trace_id=%s",
                        execution_id,
                        trace_id[:20],
                    )
                    continue

                # 全部有状态，按规则聚合
                has_error = any(
                    s.status in ("FAIL", "PART_SUC", "TIMEOUT")
                    for s in subtasks
                )
                async_status = "error" if has_error else "success"
                await self.query_service.update_execution_async_status(
                    execution_id,
                    async_status,
                )
                response.total_updated += 1
                if async_status == "success":
                    response.total_success += 1
                else:
                    response.total_error += 1
                logger.info(
                    "Updated execution async_status (timeout mode): id=%s status=%s",
                    execution_id,
                    async_status,
                )
            else:
                # 正常模式
                # 只有全部 SUC 才更新
                all_suc = all(s.status == "SUC" for s in subtasks)
                if all_suc:
                    await self.query_service.update_execution_async_status(
                        execution_id,
                        "success",
                    )
                    response.total_updated += 1
                    response.total_success += 1
                    logger.info(
                        "Updated execution async_status (normal mode): id=%s status=success",
                        execution_id,
                    )
                # 否则不更新，继续等待

        return response


# Global service instance
_sync_service: Optional[SyncService] = None


def get_sync_service() -> SyncService:
    """Get the global SyncService instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service
