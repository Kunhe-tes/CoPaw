# -*- coding: utf-8 -*-
"""Subtask sync service for external API calls and status updates.

Provides methods for:
- Syncing subtask status from external API
- Computing execution async_status from subtask statuses
"""

import logging
from typing import Optional, Tuple

import httpx

from ...config.constant import (
    ASYNC_TASK_QUERY_URL,
    ASYNC_TASK_APP_KEY,
    ASYNC_TASK_ENV_TAG,
    ASYNC_TASK_API_KEY,
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
        if return_code != "SUC000":
            return None, f"returnCode={return_code}"

        action_results = data.get("actionResults", [])
        if not action_results:
            return None, "No actionResults"

        status = action_results[0].get("status", "")
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

    async def _process_single_subtask(
        self,
        client: httpx.AsyncClient,
        subtask: SubtaskModel,
    ) -> SubtaskSyncDetailItem:
        """Process a single subtask: query status and update database."""
        detail = SubtaskSyncDetailItem(
            task_id=subtask.task_id,
            old_status=subtask.status,
        )

        status, error = await self._query_task_status(client, subtask.task_id)

        if error:
            detail.error = error
            logger.warning(
                "Failed to query task %s: %s",
                subtask.task_id[:20],
                error,
            )
            return detail

        await self.query_service.update_subtask_status(
            subtask.task_id,
            subtask.trace_id,
            status or "",  # status is non-None when error is None
        )

        detail.new_status = status
        logger.info(
            "Synced subtask status: task_id=%s status=%s",
            subtask.task_id[:20],
            status,
        )
        return detail

    async def sync_subtask_status(
        self,
        batch_size: int = BATCH_SIZE,
    ) -> SubtaskSyncStatusResponse:
        """Sync subtask statuses from external API."""
        if not self._is_configured():
            logger.warning("External API not configured, skipping sync")
            return SubtaskSyncStatusResponse(
                success=False,
                total_scanned=0,
                total_updated=0,
                total_failed=0,
            )

        subtasks = await self.query_service.get_pending_subtasks(
            limit=batch_size,
        )
        if not subtasks:
            logger.debug("No pending subtasks to sync")
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
            detail = await self._process_single_subtask(client, subtask)
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
        """Sync execution async_status from subtask statuses."""
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
            async_status = await self._compute_execution_async_status(
                execution,
            )

            if async_status is None:
                continue

            execution_id: int = execution.get("id") or 0
            if execution_id == 0:
                continue

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
                "Updated execution async_status: id=%s async_status=%s",
                execution_id,
                async_status,
            )

        return response

    async def _compute_execution_async_status(
        self,
        execution: dict,
    ) -> Optional[str]:
        """Compute async_status for an execution based on subtask statuses."""
        trace_id = execution.get("trace_id", "")
        execution_id = execution.get("id")

        if not trace_id:
            logger.warning("Execution has no trace_id: id=%s", execution_id)
            return None

        subtasks = await self.query_service.get_subtasks_by_trace_id(trace_id)

        if not subtasks:
            return "success"

        for subtask in subtasks:
            if subtask.status in ("FAIL", "PART_SUC"):
                return "error"
            if subtask.status is None or subtask.status == "":
                logger.debug(
                    "Execution has pending subtasks: id=%s trace_id=%s",
                    execution_id,
                    trace_id[:20],
                )
                return None

        return "success"


# Global service instance
_sync_service: Optional[SyncService] = None


def get_sync_service() -> SyncService:
    """Get the global SyncService instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service
