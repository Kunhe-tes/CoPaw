# -*- coding: utf-8 -*-
"""Query service for cron job and execution data.

Provides methods to query job definitions and execution history
for the frontend overview page.
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from ...database import get_db_connection
from ...models.cron import (
    CronJobModel,
    CronJobQueryParams,
    ExecutionModel,
    ExecutionQueryParams,
    PaginatedResponse,
)

# 东八区时区（北京时间）
BEIJING_TZ = ZoneInfo("Asia/Shanghai")

# 注意：数据库存储的时间已经是东八区时间（北京时间），无需再转换
# monitor_sync_client.py 在写入时已将 UTC 转为东八区，直接读取即可

logger = logging.getLogger(__name__)


# 任务定义表的时间字段（无需转换，直接读取）
JOB_TIME_FIELDS = ["created_at", "updated_at", "deleted_at"]

# 执行历史表的时间字段（无需转换，直接读取）
EXECUTION_TIME_FIELDS = [
    "scheduled_time",
    "actual_time",
    "end_time",
    "created_at",
]


def convert_row_times_direct(row: dict, time_fields: List[str]) -> dict:
    """直接读取时间字段，不做时区转换。

    数据库存储的已经是东八区时间，无需转换。

    Args:
        row: 数据库返回的行字典
        time_fields: 时间字段名列表

    Returns:
        原始行字典（时间字段不变）
    """
    return row


class QueryService:
    """Service for querying cron data."""

    def __init__(self) -> None:
        """Initialize query service."""
        pass

    async def list_jobs(
        self,
        params: CronJobQueryParams,
    ) -> PaginatedResponse[CronJobModel]:
        """List cron jobs with pagination and filters.

        Args:
            params: Query parameters

        Returns:
            Paginated response with job list
        """
        db = get_db_connection()

        # Build WHERE clause
        conditions = ["deleted_at IS NULL"]  # Exclude soft-deleted jobs
        sql_params: List = []

        if params.tenant_id:
            conditions.append("tenant_id = %s")
            sql_params.append(params.tenant_id)

        if params.bbk_id:
            conditions.append("bbk_id = %s")
            sql_params.append(params.bbk_id)

        if params.source_id:
            conditions.append("source_id = %s")
            sql_params.append(params.source_id)

        if params.creator_user_id:
            conditions.append("creator_user_id = %s")
            sql_params.append(params.creator_user_id)

        if params.status:
            conditions.append("status = %s")
            sql_params.append(params.status)

        if params.enabled is not None:
            conditions.append("enabled = %s")
            sql_params.append(params.enabled)

        where_clause = " AND ".join(conditions)

        # Count total
        count_sql = (
            f"SELECT COUNT(*) as count FROM swe_cron_jobs WHERE {where_clause}"
        )
        count_result = await db.fetch_one(count_sql, tuple(sql_params))
        total = count_result.get("count", 0) if count_result else 0

        # Query with pagination
        offset = (params.page - 1) * params.page_size
        query_sql = f"""
            SELECT * FROM swe_cron_jobs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        query_params = tuple(sql_params) + (params.page_size, offset)

        rows = await db.fetch_all(query_sql, query_params)

        # 直接读取，不做时区转换（数据库已是东八区时间）
        items = [
            CronJobModel.model_validate(
                convert_row_times_direct(row, JOB_TIME_FIELDS),
            )
            for row in rows
        ]
        # Query execution count and today's status for each job
        if items:
            job_ids = [job.id for job in items]
            placeholders = ",".join("%s" for _ in job_ids)

            # 查询总执行次数
            count_sql = f"""
                SELECT job_id, COUNT(*) as count
                FROM swe_cron_executions
                WHERE job_id IN ({placeholders})
                GROUP BY job_id
            """
            count_rows = await db.fetch_all(count_sql, tuple(job_ids))
            count_map = {
                row.get("job_id"): row.get("count", 0) for row in count_rows
            }

            # 查询今日最新执行状态（北京时间今日）
            # 数据库存储的已是东八区时间，直接用北京时间凌晨查询
            today_start = (
                datetime.now(BEIJING_TZ)
                .replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                .replace(tzinfo=None)
            )  # 去掉时区信息，因为数据库存的是 naive datetime
            today_sql = f"""
                SELECT job_id, status
                FROM swe_cron_executions
                WHERE job_id IN ({placeholders})
                AND actual_time >= %s
                ORDER BY actual_time DESC
            """
            today_rows = await db.fetch_all(
                today_sql,
                tuple(job_ids) + (today_start,),
            )
            # 取每个 job_id 的第一条记录（最新的执行状态）
            today_status_map = {}
            for row in today_rows:
                job_id = row.get("job_id")
                if job_id not in today_status_map:
                    today_status_map[job_id] = row.get("status")

            for job in items:
                job.execution_count = count_map.get(job.id, 0)
                job.today_status = today_status_map.get(job.id)

        return PaginatedResponse(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_job(self, job_id: str) -> Optional[CronJobModel]:
        """Get a single job by ID.

        Args:
            job_id: Job ID

        Returns:
            CronJobModel or None if not found
        """
        db = get_db_connection()

        row = await db.fetch_one(
            "SELECT * FROM swe_cron_jobs WHERE id = %s AND deleted_at IS NULL",
            (job_id,),
        )

        if not row:
            return None

        # 直接读取，不做时区转换（数据库已是东八区时间）
        return CronJobModel.model_validate(
            convert_row_times_direct(row, JOB_TIME_FIELDS),
        )

    async def list_executions(
        self,
        params: ExecutionQueryParams,
    ) -> PaginatedResponse[ExecutionModel]:
        """List execution history with pagination and filters.

        Args:
            params: Query parameters

        Returns:
            Paginated response with execution list
        """
        db = get_db_connection()

        # Build WHERE clause
        conditions: List[str] = []
        sql_params: List = []

        if params.job_id:
            conditions.append("e.job_id = %s")
            sql_params.append(params.job_id)

        if params.tenant_id:
            conditions.append("e.tenant_id = %s")
            sql_params.append(params.tenant_id)

        # source_id 需要通过 JOIN jobs 表筛选
        if params.source_id:
            conditions.append("j.source_id = %s")
            sql_params.append(params.source_id)

        if params.status:
            conditions.append("e.status = %s")
            sql_params.append(params.status)

        if params.start_time:
            conditions.append("e.actual_time >= %s")
            sql_params.append(params.start_time)

        if params.end_time:
            conditions.append("e.actual_time <= %s")
            sql_params.append(params.end_time)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Count total - 需要 JOIN jobs 表来支持 source_id 筛选
        count_sql = f"""
            SELECT COUNT(*) as count
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {where_clause}
        """
        count_result = await db.fetch_one(count_sql, tuple(sql_params))
        total = count_result.get("count", 0) if count_result else 0

        # Query with pagination - JOIN with jobs table to get tenant_name
        offset = (params.page - 1) * params.page_size
        query_sql = f"""
            SELECT e.*, j.tenant_name
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {where_clause}
            ORDER BY e.actual_time DESC
            LIMIT %s OFFSET %s
        """
        query_params = tuple(sql_params) + (params.page_size, offset)

        rows = await db.fetch_all(query_sql, query_params)

        # 直接读取，不做时区转换（数据库已是东八区时间）
        items = [
            ExecutionModel.model_validate(
                convert_row_times_direct(row, EXECUTION_TIME_FIELDS),
            )
            for row in rows
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_execution(
        self,
        execution_id: int,
    ) -> Optional[ExecutionModel]:
        """Get a single execution by ID.

        Args:
            execution_id: Execution ID

        Returns:
            ExecutionModel or None if not found
        """
        db = get_db_connection()

        row = await db.fetch_one(
            "SELECT * FROM swe_cron_executions WHERE id = %s",
            (execution_id,),
        )

        if not row:
            return None

        # 直接读取，不做时区转换（数据库已是东八区时间）
        return ExecutionModel.model_validate(
            convert_row_times_direct(row, EXECUTION_TIME_FIELDS),
        )

    async def get_executions_for_export(
        self,
        job_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        source_id: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 10000,
    ) -> List[ExecutionModel]:
        """Get executions for export without pagination.

        Args:
            job_id: Job ID filter
            tenant_id: Tenant ID filter
            source_id: Source ID filter (来源标识)
            status: Status filter
            start_time: Start time filter
            end_time: End time filter
            limit: Max records to return

        Returns:
            List of ExecutionModel
        """
        db = get_db_connection()

        # Build WHERE clause - 需要 JOIN jobs 表来支持 source_id 筛选
        conditions: List[str] = []
        sql_params: List = []

        if job_id:
            conditions.append("e.job_id = %s")
            sql_params.append(job_id)

        if tenant_id:
            conditions.append("e.tenant_id = %s")
            sql_params.append(tenant_id)

        # source_id 需要通过 JOIN jobs 表筛选
        if source_id:
            conditions.append("j.source_id = %s")
            sql_params.append(source_id)

        if status:
            conditions.append("e.status = %s")
            sql_params.append(status)

        if start_time:
            conditions.append("e.actual_time >= %s")
            sql_params.append(start_time)

        if end_time:
            conditions.append("e.actual_time <= %s")
            sql_params.append(end_time)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 需要 JOIN jobs 表来支持 source_id 筛选
        query_sql = f"""
            SELECT e.*
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {where_clause}
            ORDER BY e.actual_time DESC
            LIMIT %s
        """
        query_params = tuple(sql_params) + (limit,)

        rows = await db.fetch_all(query_sql, query_params)

        # 直接读取，不做时区转换（数据库已是东八区时间）
        return [
            ExecutionModel.model_validate(
                convert_row_times_direct(row, EXECUTION_TIME_FIELDS),
            )
            for row in rows
        ]

    async def get_jobs_for_export(
        self,
        tenant_id: Optional[str] = None,
        bbk_id: Optional[str] = None,
        source_id: Optional[str] = None,
        enabled: Optional[bool] = None,
        status: Optional[str] = None,
        limit: int = 10000,
    ) -> List[CronJobModel]:
        """Get jobs for export without pagination.

        Args:
            tenant_id: Tenant ID filter
            bbk_id: BBK ID filter (分行号)
            source_id: Source ID filter (来源标识)
            enabled: Enabled filter (是否启用)
            status: Status filter
            limit: Max records to return

        Returns:
            List of CronJobModel
        """
        db = get_db_connection()

        # Build WHERE clause
        conditions = ["deleted_at IS NULL"]
        sql_params: List = []

        if tenant_id:
            conditions.append("tenant_id = %s")
            sql_params.append(tenant_id)

        if bbk_id:
            conditions.append("bbk_id = %s")
            sql_params.append(bbk_id)

        if source_id:
            conditions.append("source_id = %s")
            sql_params.append(source_id)

        if enabled is not None:
            conditions.append("enabled = %s")
            sql_params.append(enabled)

        if status:
            conditions.append("status = %s")
            sql_params.append(status)

        where_clause = " AND ".join(conditions)

        query_sql = f"""
            SELECT * FROM swe_cron_jobs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s
        """
        query_params = tuple(sql_params) + (limit,)

        rows = await db.fetch_all(query_sql, query_params)

        # 直接读取，不做时区转换（数据库已是东八区时间）
        items = [
            CronJobModel.model_validate(
                convert_row_times_direct(row, JOB_TIME_FIELDS),
            )
            for row in rows
        ]
        # Query execution count for each job
        if items:
            job_ids = [job.id for job in items]
            placeholders = ",".join("%s" for _ in job_ids)
            count_sql = f"""
                SELECT job_id, COUNT(*) as count
                FROM swe_cron_executions
                WHERE job_id IN ({placeholders})
                GROUP BY job_id
            """
            count_rows = await db.fetch_all(count_sql, tuple(job_ids))
            count_map = {
                row.get("job_id"): row.get("count", 0) for row in count_rows
            }
            for job in items:
                job.execution_count = count_map.get(job.id, 0)

        return items

    async def get_filter_options(self) -> dict:
        """获取所有筛选项的下拉选项列表。

        从任务表和执行表中聚合获取可选值，用于前端下拉框。

        Returns:
            包含各筛选项列表的字典
        """
        db = get_db_connection()

        # 获取用户列表（按 tenant_id 分组去重，避免同一用户多条记录）
        users_sql = """
            SELECT tenant_id, MAX(tenant_name) as tenant_name
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL AND tenant_id IS NOT NULL AND tenant_id != ''
            GROUP BY tenant_id
            ORDER BY tenant_name, tenant_id
        """
        users_rows = await db.fetch_all(users_sql)
        users = [
            {
                "value": row["tenant_id"],
                "label": f"{row['tenant_name'] or ''}/{row['tenant_id']}",
            }
            for row in users_rows
        ]

        # 获取分行列表（bbk_id）
        bbk_sql = """
            SELECT DISTINCT bbk_id
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL AND bbk_id IS NOT NULL AND bbk_id != ''
            ORDER BY bbk_id
        """
        bbk_rows = await db.fetch_all(bbk_sql)
        bbk_ids = [
            {"value": row["bbk_id"], "label": row["bbk_id"]}
            for row in bbk_rows
        ]

        # 获取渠道列表（channel）
        channel_sql = """
            SELECT DISTINCT channel
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL AND channel IS NOT NULL AND channel != ''
            ORDER BY channel
        """
        channel_rows = await db.fetch_all(channel_sql)
        channels = [
            {"value": row["channel"], "label": row["channel"]}
            for row in channel_rows
        ]

        # 获取来源/平台列表（source_id）
        source_sql = """
            SELECT DISTINCT source_id
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL AND source_id IS NOT NULL AND source_id != ''
            ORDER BY source_id
        """
        source_rows = await db.fetch_all(source_sql)
        source_ids = [
            {"value": row["source_id"], "label": row["source_id"]}
            for row in source_rows
        ]

        # 获取任务名称列表（name）
        job_names_sql = """
            SELECT DISTINCT name
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL AND name IS NOT NULL AND name != ''
            ORDER BY name
        """
        job_names_rows = await db.fetch_all(job_names_sql)
        job_names = [
            {"value": row["name"], "label": row["name"]}
            for row in job_names_rows
        ]

        # 获取任务ID列表（用于执行记录筛选）
        job_ids_sql = """
            SELECT DISTINCT id, name
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL
            ORDER BY name
        """
        job_ids_rows = await db.fetch_all(job_ids_sql)
        job_ids = [
            {"value": row["id"], "label": row["name"] or row["id"]}
            for row in job_ids_rows
        ]

        return {
            "users": users,
            "bbk_ids": bbk_ids,
            "channels": channels,
            "source_ids": source_ids,
            "job_names": job_names,
            "job_ids": job_ids,
        }

    async def mark_job_as_read(self, job_id: str) -> int:
        """标记任务及其历史执行记录为已读。

        将指定任务的所有成功执行的未读记录标记为已读，
        同时更新该任务之前所有未读的成功执行记录。

        Args:
            job_id: 任务ID

        Returns:
            更新的记录数量
        """
        db = get_db_connection()
        # 数据库存储的是 naive datetime（东八区时间），去掉时区信息
        now = datetime.now(BEIJING_TZ).replace(tzinfo=None)

        # 更新该任务所有成功的未读执行记录
        update_sql = """
            UPDATE swe_cron_executions
            SET is_read = TRUE, read_at = %s
            WHERE job_id = %s
            AND status = 'success'
            AND is_read = FALSE
        """
        await db.execute(update_sql, (now, job_id))

        # 获取更新的记录数量
        count_sql = """
            SELECT COUNT(*) as count
            FROM swe_cron_executions
            WHERE job_id = %s AND status = 'success' AND is_read = TRUE
        """
        result = await db.fetch_one(count_sql, (job_id,))
        return result.get("count", 0) if result else 0

    async def get_unread_count(self, tenant_id: Optional[str] = None) -> dict:
        """获取未读任务数量统计。

        按任务分组统计未读的成功执行记录数量，
        用于前端展示未读提醒。

        Args:
            tenant_id: 租户ID筛选（可选）

        Returns:
            包含各任务未读数量的字典
        """
        db = get_db_connection()

        conditions = ["status = 'success'", "is_read = FALSE"]
        sql_params: List = []

        if tenant_id:
            conditions.append("tenant_id = %s")
            sql_params.append(tenant_id)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT job_id, job_name, COUNT(*) as unread_count
            FROM swe_cron_executions
            WHERE {where_clause}
            GROUP BY job_id, job_name
            ORDER BY unread_count DESC
        """
        rows = await db.fetch_all(
            sql,
            tuple(sql_params) if sql_params else None,
        )

        return {
            "items": [
                {
                    "job_id": row["job_id"],
                    "job_name": row["job_name"] or row["job_id"],
                    "unread_count": row["unread_count"],
                }
                for row in rows
            ],
            "total_unread": sum(row["unread_count"] for row in rows),
        }


# Global query service instance
_query_service: Optional[QueryService] = None


def get_query_service() -> QueryService:
    """Get the query service instance.

    Returns:
        QueryService instance
    """
    global _query_service
    if _query_service is None:
        _query_service = QueryService()
    return _query_service
