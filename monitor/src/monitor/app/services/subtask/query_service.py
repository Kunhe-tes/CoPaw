# -*- coding: utf-8 -*-
"""Subtask query service for database operations.

Provides methods for creating and querying subtask records.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from ...database.connection import get_db_connection
from ...models.subtask import SubtaskModel, SubtaskCreateResponse
from ....utils.bbk import normalize_bbk_id_to_primary

logger = logging.getLogger(__name__)

# 每批处理数量
BATCH_SIZE = 50


class QueryService:
    """Service for subtask database operations."""

    def __init__(self, db=None):
        """Initialize query service.

        Args:
            db: Database connection
        """
        self.db = db

    async def create_subtask(
        self,
        trace_id: str,
        task_id: str,
        filename: str,
        task_type: Optional[str] = None,
        custuid: Optional[str] = None,
        bbk_org_id: Optional[str] = None,
        cust_nm: Optional[str] = None,
        notification_content_wplus: Optional[str] = None,
        notification_content_zhaohu: Optional[str] = None,
        need_notification: int = 1,
        template_id: Optional[int] = None,
        result_id: Optional[str] = None,
    ) -> SubtaskCreateResponse:
        """Create a subtask record.

        Args:
            trace_id: Main task trace_id
            task_id: Subtask task_id
            filename: File name
            task_type: Task type (list/plan)
            custuid: Customer ID
            bbk_org_id: Customer branch ID for reference
            cust_nm: Customer name
            notification_content_wplus: W+ channel notification content
            notification_content_zhaohu: Zhaohu channel notification content
            need_notification: Whether notification is needed (0 or 1)
            template_id: Template ID for html content rendering
            result_id: ES document ID for reference

        Returns:
            SubtaskCreateResponse with creation result
        """
        if not self.db:
            logger.warning("Database not connected, skipping subtask creation")
            return SubtaskCreateResponse(
                success=False,
                message="Database not connected",
            )

        # Check if already exists (idempotent)
        existing = await self._get_subtask_by_trace_and_task(trace_id, task_id)
        if existing:
            logger.debug(
                "Subtask already exists: trace_id=%s task_id=%s",
                trace_id,
                task_id,
            )
            return SubtaskCreateResponse(
                success=True,
                id=existing.id,
                message="Subtask already exists",
            )

        # Insert new record
        query = """
            INSERT INTO swe_cron_subtasks (
                trace_id,
                task_id,
                filename,
                task_type,
                custuid,
                bbk_org_id,
                cust_nm,
                notification_content_wplus,
                notification_content_zhaohu,
                need_notification,
                status,
                info,
                created_at,
                updated_at,
                template_id,
                result_id
            )
            VALUES (%s, %s, %s, %s, %s, %s,%s, %s, %s, %s, NULL, '', %s, NULL, %s, %s)
        """
        now = datetime.now()
        await self.db.execute(
            query,
            (
                trace_id,
                task_id,
                filename,
                task_type,
                custuid,
                bbk_org_id,
                cust_nm,
                notification_content_wplus,
                notification_content_zhaohu,
                need_notification,
                now,
                template_id,
                result_id,
            ),
        )

        # Get the inserted ID
        id_query = "SELECT LAST_INSERT_ID() AS id"
        row = await self.db.fetch_one(id_query)
        inserted_id = row.get("id") if row else None

        logger.info(
            "Created subtask: trace_id=%s task_id=%s filename=%s id=%s",
            trace_id,
            task_id,
            filename,
            inserted_id,
        )

        return SubtaskCreateResponse(
            success=True,
            id=inserted_id,
            message="Subtask created",
        )

    async def _get_subtask_by_trace_and_task(
        self,
        trace_id: str,
        task_id: str,
    ) -> Optional[SubtaskModel]:
        """Get subtask by trace_id and task_id.

        Args:
            trace_id: Main task trace_id
            task_id: Subtask task_id

        Returns:
            SubtaskModel or None
        """
        if not self.db:
            return None

        query = """
            SELECT id, trace_id, task_id, filename, task_type, custuid, cust_nm,
                   notification_content_wplus, notification_content_zhaohu,
                   need_notification, status, info, created_at, updated_at
            FROM swe_cron_subtasks
            WHERE trace_id = %s AND task_id = %s
        """
        row = await self.db.fetch_one(query, (trace_id, task_id))
        if not row:
            return None

        return SubtaskModel(
            id=row.get("id"),
            trace_id=row.get("trace_id") or "",
            task_id=row.get("task_id") or "",
            filename=row.get("filename") or "",
            task_type=row.get("task_type"),
            custuid=row.get("custuid"),
            cust_nm=row.get("cust_nm"),
            notification_content_wplus=row.get("notification_content_wplus"),
            notification_content_zhaohu=row.get("notification_content_zhaohu"),
            need_notification=row.get("need_notification", 1),
            status=row.get("status"),
            info=row.get("info") or "",
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    async def get_pending_subtasks(
        self,
        limit: int = BATCH_SIZE,
    ) -> list[SubtaskModel]:
        """Get subtasks with NULL or empty status.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of SubtaskModel
        """
        if not self.db:
            return []

        query = """
            SELECT id, trace_id, task_id, filename, task_type, custuid, cust_nm,
                   notification_content_wplus, notification_content_zhaohu,
                   need_notification, status, info, created_at, updated_at
            FROM swe_cron_subtasks
            WHERE status IS NULL OR status = ''
            ORDER BY created_at ASC
            LIMIT %s
        """
        rows = await self.db.fetch_all(query, (limit,))
        return [
            SubtaskModel(
                id=row.get("id"),
                trace_id=row.get("trace_id") or "",
                task_id=row.get("task_id") or "",
                filename=row.get("filename") or "",
                task_type=row.get("task_type"),
                custuid=row.get("custuid"),
                cust_nm=row.get("cust_nm"),
                notification_content_wplus=row.get(
                    "notification_content_wplus",
                ),
                notification_content_zhaohu=row.get(
                    "notification_content_zhaohu",
                ),
                need_notification=row.get("need_notification", 1),
                status=row.get("status"),
                info=row.get("info") or "",
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
            for row in rows
        ]

    async def get_today_pending_subtasks(
        self,
        limit: int = BATCH_SIZE,
    ) -> list[SubtaskModel]:
        """Get subtasks for status sync.

        查询范围：
        只查询无状态的子任务（status IS NULL OR status = ''），不限制时间

        Args:
            limit: Maximum number of records to return

        Returns:
            List of SubtaskModel
        """
        if not self.db:
            return []

        query = """
            SELECT id, trace_id, task_id, filename, task_type, custuid, cust_nm,
                   notification_content_wplus, notification_content_zhaohu,
                   need_notification, status, info, created_at, updated_at
            FROM swe_cron_subtasks
            WHERE status IS NULL OR status = ''
            ORDER BY created_at ASC
            LIMIT %s
        """
        rows = await self.db.fetch_all(query, (limit,))
        return [
            SubtaskModel(
                id=row.get("id"),
                trace_id=row.get("trace_id") or "",
                task_id=row.get("task_id") or "",
                filename=row.get("filename") or "",
                task_type=row.get("task_type"),
                custuid=row.get("custuid"),
                cust_nm=row.get("cust_nm"),
                notification_content_wplus=row.get(
                    "notification_content_wplus",
                ),
                notification_content_zhaohu=row.get(
                    "notification_content_zhaohu",
                ),
                need_notification=row.get("need_notification", 1),
                status=row.get("status"),
                info=row.get("info") or "",
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
            for row in rows
        ]

    async def get_subtasks_by_trace_id(
        self,
        trace_id: str,
    ) -> list[SubtaskModel]:
        """Get all subtasks for a trace_id.

        Args:
            trace_id: Main task trace_id

        Returns:
            List of SubtaskModel
        """
        if not self.db:
            return []

        query = """
            SELECT id, trace_id, task_id, filename, task_type, custuid, cust_nm,
                   notification_content_wplus, notification_content_zhaohu,
                   need_notification, status, info, created_at, updated_at
            FROM swe_cron_subtasks
            WHERE trace_id = %s
        """
        rows = await self.db.fetch_all(query, (trace_id,))
        return [
            SubtaskModel(
                id=row.get("id"),
                trace_id=row.get("trace_id") or "",
                task_id=row.get("task_id") or "",
                filename=row.get("filename") or "",
                task_type=row.get("task_type"),
                custuid=row.get("custuid"),
                cust_nm=row.get("cust_nm"),
                notification_content_wplus=row.get(
                    "notification_content_wplus",
                ),
                notification_content_zhaohu=row.get(
                    "notification_content_zhaohu",
                ),
                need_notification=row.get("need_notification", 1),
                status=row.get("status"),
                info=row.get("info") or "",
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
            for row in rows
        ]

    async def update_subtask_status(
        self,
        task_id: str,
        trace_id: str,
        status: str,
    ) -> bool:
        """Update subtask status.

        Args:
            task_id: Subtask task_id
            trace_id: Main task trace_id
            status: New status value

        Returns:
            True if updated, False otherwise
        """
        if not self.db:
            return False

        query = """
            UPDATE swe_cron_subtasks
            SET status = %s, updated_at = %s
            WHERE task_id = %s AND trace_id = %s
        """
        now = datetime.now()
        await self.db.execute(query, (status, now, task_id, trace_id))

        logger.debug(
            "Updated subtask status: task_id=%s trace_id=%s status=%s",
            task_id[:20],
            trace_id[:20],
            status,
        )
        return True

    async def get_pending_executions(
        self,
        limit: int = 100,
    ) -> list[dict]:
        """Get executions with NULL or empty async_status.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of execution dicts with id and trace_id
        """
        if not self.db:
            return []

        query = """
            SELECT id, trace_id
            FROM swe_cron_executions
            WHERE async_status IS NULL OR async_status = ''
            ORDER BY created_at ASC
            LIMIT %s
        """
        rows = await self.db.fetch_all(query, (limit,))
        return [
            {
                "id": row.get("id"),
                "trace_id": row.get("trace_id") or "",
            }
            for row in rows
        ]

    async def update_execution_async_status(
        self,
        execution_id: int,
        async_status: str,
    ) -> bool:
        """Update execution async_status.

        Args:
            execution_id: Execution ID
            async_status: New async_status value (success/error)

        Returns:
            True if updated, False otherwise
        """
        if not self.db:
            return False

        query = """
            UPDATE swe_cron_executions
            SET async_status = %s
            WHERE id = %s
        """
        await self.db.execute(query, (async_status, execution_id))

        logger.debug(
            "Updated execution async_status: id=%s async_status=%s",
            execution_id,
            async_status,
        )
        return True

    async def _get_success_execution_candidates(self) -> list[dict]:
        """Get executions that are ready to become async success."""
        query = """
            SELECT
                e.id AS execution_id,
                e.job_id,
                e.trace_id,
                e.actual_time,
                e.created_at,
                j.tenant_id,
                j.bbk_id,
                j.source_id,
                j.skill_ids
            FROM swe_cron_executions e
            JOIN swe_cron_jobs j ON j.id = e.job_id
            WHERE (e.async_status IS NULL OR e.async_status = '')
              AND e.status = 'success'
              AND NOT EXISTS (
                  SELECT 1 FROM swe_cron_subtasks s
                  WHERE s.trace_id = e.trace_id
                  AND (s.status IS NULL OR s.status = '')
              )
              AND NOT EXISTS (
                  SELECT 1 FROM swe_cron_subtasks s
                  WHERE s.trace_id = e.trace_id
                  AND s.status IN ('FAIL', 'PART_SUC', 'TIMEOUT')
              )
        """
        return await self.db.fetch_all(query)

    def _split_skill_ids(self, skill_ids: Optional[str]) -> list[str]:
        """Split comma-separated skill ids while preserving order."""
        values = []
        seen = set()
        for skill_id in (skill_ids or "").split(","):
            normalized = skill_id.strip()
            if normalized and normalized not in seen:
                values.append(normalized)
                seen.add(normalized)
        return values

    async def _get_success_subtasks_for_trace(
        self,
        trace_id: str,
    ) -> list[dict]:
        """Get successful list/plan subtasks for a trace."""
        query = """
            SELECT
                id AS subtask_id,
                trace_id,
                task_id,
                filename,
                task_type,
                custuid,
                cust_nm,
                bbk_org_id,
                template_id,
                result_id,
                status,
                created_at
            FROM swe_cron_subtasks
            WHERE trace_id = %s
              AND status = 'SUC'
              AND task_type IN ('list', 'plan')
              AND template_id IS NOT NULL
              AND template_id > 0
              AND result_id IS NOT NULL
              AND result_id <> ''
        """
        return await self.db.fetch_all(query, (trace_id,))

    async def _mark_previous_result_index_stale(
        self,
        row: dict,
    ) -> None:
        """Mark previous successful result-index rows as non-latest."""
        if row["result_type"] == "plan":
            query = """
                UPDATE swe_cron_result_index
                SET is_latest_success = 0, updated_at = %s
                WHERE source_id = %s
                  AND tenant_id = %s
                  AND first_bbk_id = %s
                  AND bbk_org_id = %s
                  AND skill_id = %s
                  AND job_id = %s
                  AND result_type = %s
                  AND custuid = %s
                  AND is_latest_success = 1
                  AND execution_id <> %s
            """
            params = (
                datetime.now(),
                row["source_id"],
                row["tenant_id"],
                row["first_bbk_id"],
                row["bbk_org_id"],
                row["skill_id"],
                row["job_id"],
                row["result_type"],
                row["custuid"],
                row["execution_id"],
            )
        else:
            query = """
                UPDATE swe_cron_result_index
                SET is_latest_success = 0, updated_at = %s
                WHERE source_id = %s
                  AND tenant_id = %s
                  AND first_bbk_id = %s
                  AND bbk_org_id = %s
                  AND skill_id = %s
                  AND job_id = %s
                  AND result_type = %s
                  AND is_latest_success = 1
                  AND execution_id <> %s
            """
            params = (
                datetime.now(),
                row["source_id"],
                row["tenant_id"],
                row["first_bbk_id"],
                row["bbk_org_id"],
                row["skill_id"],
                row["job_id"],
                row["result_type"],
                row["execution_id"],
            )
        await self.db.execute(query, params)

    async def _upsert_result_index_row(self, row: dict) -> None:
        """Insert or update a result-index row."""
        query = """
            INSERT INTO swe_cron_result_index (
                source_id,
                tenant_id,
                first_bbk_id,
                bbk_org_id,
                custuid,
                cust_nm,
                skill_id,
                job_id,
                execution_id,
                trace_id,
                subtask_id,
                task_id,
                result_type,
                template_id,
                result_id,
                filename,
                status,
                is_latest_success,
                execution_at,
                updated_at,
                expire_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, 1, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                source_id = VALUES(source_id),
                tenant_id = VALUES(tenant_id),
                first_bbk_id = VALUES(first_bbk_id),
                bbk_org_id = VALUES(bbk_org_id),
                custuid = VALUES(custuid),
                cust_nm = VALUES(cust_nm),
                job_id = VALUES(job_id),
                execution_id = VALUES(execution_id),
                trace_id = VALUES(trace_id),
                task_id = VALUES(task_id),
                result_type = VALUES(result_type),
                template_id = VALUES(template_id),
                result_id = VALUES(result_id),
                filename = VALUES(filename),
                status = VALUES(status),
                is_latest_success = 1,
                execution_at = VALUES(execution_at),
                updated_at = VALUES(updated_at),
                expire_at = VALUES(expire_at)
        """
        params = (
            row["source_id"],
            row["tenant_id"],
            row["first_bbk_id"],
            row["bbk_org_id"],
            row["custuid"],
            row["cust_nm"],
            row["skill_id"],
            row["job_id"],
            row["execution_id"],
            row["trace_id"],
            row["subtask_id"],
            row["task_id"],
            row["result_type"],
            row["template_id"],
            row["result_id"],
            row["filename"],
            row["status"],
            row["execution_at"],
            datetime.now(),
            row["expire_at"],
        )
        await self.db.execute(query, params)

    async def _index_success_execution_results(
        self,
        executions: list[dict],
    ) -> int:
        """Write query-index rows for successful executions."""
        indexed_count = 0
        for execution in executions:
            skill_ids = self._split_skill_ids(execution.get("skill_ids"))
            if not skill_ids:
                continue

            subtasks = await self._get_success_subtasks_for_trace(
                execution.get("trace_id") or "",
            )
            execution_at = (
                execution.get("actual_time")
                or execution.get("created_at")
                or datetime.now()
            )
            expire_at = execution_at + timedelta(days=30)

            for subtask in subtasks:
                result_type = subtask.get("task_type")
                bbk_org_id = subtask.get("bbk_org_id") or ""
                first_bbk_id = (
                    normalize_bbk_id_to_primary(bbk_org_id)
                    or execution.get("bbk_id")
                    or ""
                )
                for skill_id in skill_ids:
                    row = {
                        "source_id": execution.get("source_id") or "",
                        "tenant_id": execution.get("tenant_id") or "",
                        "first_bbk_id": first_bbk_id,
                        "bbk_org_id": bbk_org_id,
                        "custuid": subtask.get("custuid") or "",
                        "cust_nm": subtask.get("cust_nm"),
                        "skill_id": skill_id,
                        "job_id": execution.get("job_id") or "",
                        "execution_id": execution.get("execution_id"),
                        "trace_id": execution.get("trace_id") or "",
                        "subtask_id": subtask.get("subtask_id"),
                        "task_id": subtask.get("task_id") or "",
                        "result_type": result_type,
                        "template_id": subtask.get("template_id"),
                        "result_id": subtask.get("result_id"),
                        "filename": subtask.get("filename"),
                        "status": subtask.get("status"),
                        "execution_at": execution_at,
                        "expire_at": expire_at,
                    }
                    await self._mark_previous_result_index_stale(row)
                    await self._upsert_result_index_row(row)
                    indexed_count += 1
        return indexed_count

    async def batch_update_execution_async_status(
        self,
    ) -> Tuple[int, int, int]:
        """Batch update execution async_status using JOIN with subtasks.

        使用 SQL JOIN 批量更新，高效处理大量数据。
        同时更新 need_notification 字段：
        - 若不存在子任务则 need_notification = 1
        - 若存在子任务则按照 task_type='list' 的 need_notification 字段更新

        Returns:
            Tuple of (success_count, error_count, indexed_count)
        """
        if not self.db:
            return 0, 0, 0

        success_executions = await self._get_success_execution_candidates()

        # 更新 success：没有 pending 子任务且没有 error 子任务
        # 同时设置 need_notification：
        # - 无子任务时设为 1
        # - 有子任务时取 task_type='list' 的 need_notification 值
        success_query = """
            UPDATE swe_cron_executions e
            SET
                async_status = 'success',
                need_notification = COALESCE(
                    (
                        SELECT s.need_notification
                        FROM swe_cron_subtasks s
                        WHERE s.trace_id = e.trace_id
                        AND s.task_type = 'list'
                        LIMIT 1
                    ),
                    1
                )
            WHERE (e.async_status IS NULL OR e.async_status = '')
            AND e.status = 'success'
            AND NOT EXISTS (
                SELECT 1 FROM swe_cron_subtasks s
                WHERE s.trace_id = e.trace_id
                AND (s.status IS NULL OR s.status = '')
            )
            AND NOT EXISTS (
                SELECT 1 FROM swe_cron_subtasks s
                WHERE s.trace_id = e.trace_id
                AND s.status IN ('FAIL', 'PART_SUC', 'TIMEOUT')
            )
        """
        await self.db.execute(success_query)
        success_row = await self.db.fetch_one(
            "SELECT ROW_COUNT() AS count",
        )
        success_count = success_row.get("count", 0) if success_row else 0
        indexed_count = await self._index_success_execution_results(
            success_executions,
        )

        # 更新 error：有 error 子任务且没有 pending 子任务
        # 同时设置 need_notification 同上逻辑
        error_query = """
            UPDATE swe_cron_executions e
            SET
                async_status = 'error',
                need_notification = COALESCE(
                    (
                        SELECT s.need_notification
                        FROM swe_cron_subtasks s
                        WHERE s.trace_id = e.trace_id
                        AND s.task_type = 'list'
                        LIMIT 1
                    ),
                    1
                )
            WHERE (e.async_status IS NULL OR e.async_status = '')
            AND EXISTS (
                SELECT 1 FROM swe_cron_subtasks s
                WHERE s.trace_id = e.trace_id
                AND s.status IN ('FAIL', 'PART_SUC', 'TIMEOUT')
            )
            AND NOT EXISTS (
                SELECT 1 FROM swe_cron_subtasks s
                WHERE s.trace_id = e.trace_id
                AND (s.status IS NULL OR s.status = '')
            )
        """
        await self.db.execute(error_query)
        error_row = await self.db.fetch_one(
            "SELECT ROW_COUNT() AS count",
        )
        error_count = error_row.get("count", 0) if error_row else 0

        logger.info(
            "Batch updated execution async_status and need_notification: "
            "success=%d error=%d indexed=%d",
            success_count,
            error_count,
            indexed_count,
        )
        return success_count, error_count, indexed_count


# Global service instance
_query_service: Optional[QueryService] = None


def get_query_service() -> QueryService:
    """Get the global QueryService instance.

    Returns:
        QueryService instance
    """
    global _query_service
    if _query_service is None:
        db = get_db_connection()
        _query_service = QueryService(db=db)
    return _query_service
