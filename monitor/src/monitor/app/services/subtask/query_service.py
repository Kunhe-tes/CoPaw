# -*- coding: utf-8 -*-
"""Subtask query service for database operations.

Provides methods for creating and querying subtask records.
"""

import logging
from datetime import datetime
from typing import Optional

from ...database.connection import get_db_connection
from ...models.subtask import SubtaskModel, SubtaskCreateResponse

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
    ) -> SubtaskCreateResponse:
        """Create a subtask record.

        Args:
            trace_id: Main task trace_id
            task_id: Subtask task_id
            filename: File name

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
                trace_id[:20],
                task_id[:20],
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
                status,
                info,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, NULL, '', %s, NULL)
        """
        now = datetime.now()
        await self.db.execute(query, (trace_id, task_id, filename, now))

        # Get the inserted ID
        id_query = "SELECT LAST_INSERT_ID() AS id"
        row = await self.db.fetch_one(id_query)
        inserted_id = row.get("id") if row else None

        logger.info(
            "Created subtask: trace_id=%s task_id=%s filename=%s id=%s",
            trace_id[:20],
            task_id[:20],
            filename[:30],
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
            SELECT id, trace_id, task_id, filename, status, info, created_at, updated_at
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
            SELECT id, trace_id, task_id, filename, status, info, created_at, updated_at
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
            SELECT id, trace_id, task_id, filename, status, info, created_at, updated_at
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
            ORDER BY created_at DESC
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
