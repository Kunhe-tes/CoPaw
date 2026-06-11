# -*- coding: utf-8 -*-
"""Query service for cron job and execution data.

Provides methods to query job definitions and execution history
for the frontend overview page.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Any, Dict
from zoneinfo import ZoneInfo

from ...database import get_db_connection
from ...models.cron import (
    CronOverviewBranchExecutionItem,
    CronOverviewBranchReadItem,
    CronOverviewDistributionItem,
    CronOverviewMetricItem,
    CronOverviewResponse,
    CronJobModel,
    CronJobQueryParams,
    ExecutionModel,
    ExecutionQueryParams,
    PaginatedResponse,
    SubscriptionDetailItem,
    SubscriptionOverviewItem,
    UnreadCountResponse,
)
from ....utils.bbk import get_bbk_name_by_id

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
    "notification_due_at",
    "notification_sent_at",
    "notification_locked_at",
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

        if params.job_origin:
            conditions.append("job_origin = %s")
            sql_params.append(params.job_origin)

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

    async def get_job(
        self,
        job_id: str,
        source_id: Optional[str] = None,
    ) -> Optional[CronJobModel]:
        """Get a single job by ID.

        Args:
            job_id: Job ID
            source_id: Source ID filter

        Returns:
            CronJobModel or None if not found
        """
        db = get_db_connection()
        conditions = ["id = %s", "deleted_at IS NULL"]
        sql_params: List = [job_id]

        if source_id:
            conditions.append("source_id = %s")
            sql_params.append(source_id)

        row = await db.fetch_one(
            f"SELECT * FROM swe_cron_jobs WHERE {' AND '.join(conditions)}",
            tuple(sql_params),
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
            if params.status == "error":
                conditions.append("j.status != 'deleted'")

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
        source_id: Optional[str] = None,
    ) -> Optional[ExecutionModel]:
        """Get a single execution by ID.

        Args:
            execution_id: Execution ID
            source_id: Source ID filter

        Returns:
            ExecutionModel or None if not found
        """
        db = get_db_connection()
        conditions = ["e.id = %s"]
        sql_params: List = [execution_id]

        if source_id:
            conditions.append("j.source_id = %s")
            sql_params.append(source_id)

        row = await db.fetch_one(
            f"""
            SELECT e.*
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {' AND '.join(conditions)}
            """,
            tuple(sql_params),
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

    async def get_filter_options(
        self,
        source_id: Optional[str] = None,
    ) -> dict:
        """获取所有筛选项的下拉选项列表。

        从任务表和执行表中聚合获取可选值，用于前端下拉框。

        Args:
            source_id: Source ID filter

        Returns:
            包含各筛选项列表的字典
        """
        db = get_db_connection()
        source_condition = ""
        source_params: Tuple = ()
        if source_id:
            source_condition = " AND source_id = %s"
            source_params = (source_id,)

        # 获取用户列表（按 tenant_id 分组去重，避免同一用户多条记录）
        users_sql = """
            SELECT tenant_id, MAX(tenant_name) as tenant_name
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL
                AND tenant_id IS NOT NULL
                AND tenant_id != ''
                {source_condition}
            GROUP BY tenant_id
            ORDER BY tenant_name, tenant_id
        """.format(source_condition=source_condition)
        users_rows = await db.fetch_all(users_sql, source_params)
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
            WHERE deleted_at IS NULL
                AND bbk_id IS NOT NULL
                AND bbk_id != ''
                {source_condition}
            ORDER BY bbk_id
        """.format(source_condition=source_condition)
        bbk_rows = await db.fetch_all(bbk_sql, source_params)
        bbk_ids = [
            {"value": row["bbk_id"], "label": row["bbk_id"]}
            for row in bbk_rows
        ]

        # 获取渠道列表（channel）
        channel_sql = """
            SELECT DISTINCT channel
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL
                AND channel IS NOT NULL
                AND channel != ''
                {source_condition}
            ORDER BY channel
        """.format(source_condition=source_condition)
        channel_rows = await db.fetch_all(channel_sql, source_params)
        channels = [
            {"value": row["channel"], "label": row["channel"]}
            for row in channel_rows
        ]

        # 获取来源/平台列表（source_id）
        source_sql = """
            SELECT DISTINCT source_id
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL
                AND source_id IS NOT NULL
                AND source_id != ''
                {source_condition}
            ORDER BY source_id
        """.format(source_condition=source_condition)
        source_rows = await db.fetch_all(source_sql, source_params)
        source_ids = [
            {"value": row["source_id"], "label": row["source_id"]}
            for row in source_rows
        ]

        # 获取任务名称列表（name）
        job_names_sql = """
            SELECT DISTINCT name
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL
                AND name IS NOT NULL
                AND name != ''
                {source_condition}
            ORDER BY name
        """.format(source_condition=source_condition)
        job_names_rows = await db.fetch_all(job_names_sql, source_params)
        job_names = [
            {"value": row["name"], "label": row["name"]}
            for row in job_names_rows
        ]

        # 获取任务ID列表（用于执行记录筛选）
        job_ids_sql = """
            SELECT DISTINCT id, name
            FROM swe_cron_jobs
            WHERE deleted_at IS NULL
                {source_condition}
            ORDER BY name
        """.format(source_condition=source_condition)
        job_ids_rows = await db.fetch_all(job_ids_sql, source_params)
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

    async def get_overview(
        self,
        *,
        tenant_id: Optional[str] = None,
        bbk_id: Optional[str] = None,
        source_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> CronOverviewResponse:
        """Return page-shaped aggregate data for the cron overview."""
        db = get_db_connection()
        start_time, end_time = self._resolve_today_range(start_time, end_time)
        job_where, job_params, exec_where, exec_params = self._build_overview_clauses(
            tenant_id=tenant_id,
            bbk_id=bbk_id,
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
        )
        job_summary = await self._fetch_overview_job_summary(
            db,
            job_where,
            job_params,
        )
        prev_job_summary = await self._fetch_previous_job_summary(
            db,
            tenant_id=tenant_id,
            bbk_id=bbk_id,
            source_id=source_id,
            start_time=start_time,
        )
        exec_summary = await self._fetch_overview_execution_summary(
            db,
            exec_where,
            exec_params,
        )
        prev_exec_summary = await self._fetch_previous_execution_summary(
            db,
            tenant_id=tenant_id,
            bbk_id=bbk_id,
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
        )

        return CronOverviewResponse(
            start_time=start_time,
            end_time=end_time,
            metrics=self._build_overview_metrics(
                job_summary,
                prev_job_summary,
                exec_summary,
                prev_exec_summary,
            ),
            task_status=self._build_task_status_distribution(job_summary),
            execution_result=await self._fetch_execution_result_distribution(
                db,
                exec_where,
                exec_params,
            ),
            read_status=await self._fetch_read_status_distribution(
                db,
                exec_where,
                exec_params,
            ),
            failure_reasons=await self._fetch_failure_reason_distribution(
                db,
                exec_where,
                exec_params,
            ),
            branch_tasks=await self._fetch_branch_task_distribution(
                db,
                job_where,
                job_params,
            ),
            branch_execution=await self._fetch_branch_execution_distribution(
                db,
                exec_where,
                exec_params,
            ),
            branch_read=await self._fetch_branch_read_distribution(
                db,
                exec_where,
                exec_params,
            ),
        )

    def _build_overview_clauses(
        self,
        *,
        tenant_id: Optional[str],
        bbk_id: Optional[str],
        source_id: Optional[str],
        start_time: datetime,
        end_time: datetime,
    ) -> Tuple[str, List, str, List]:
        job_conditions, job_params = self._build_overview_job_conditions(
            tenant_id=tenant_id,
            bbk_id=bbk_id,
            source_id=source_id,
        )
        exec_conditions, exec_params = self._build_overview_execution_conditions(
            tenant_id=tenant_id,
            bbk_id=bbk_id,
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
        )
        return (
            " AND ".join(job_conditions),
            job_params,
            " AND ".join(exec_conditions),
            exec_params,
        )

    async def _fetch_overview_job_summary(
        self,
        db: Any,
        job_where: str,
        job_params: List,
    ) -> Dict[str, Any]:
        row = await db.fetch_one(
            f"""
            SELECT
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN job_origin = 'subscription' THEN 1 ELSE 0 END)
                    AS subscription_tasks,
                SUM(CASE WHEN job_origin != 'subscription' THEN 1 ELSE 0 END)
                    AS manual_tasks,
                SUM(
                    CASE
                        WHEN enabled = 1 AND status = 'active'
                        THEN 1 ELSE 0
                    END
                ) AS active_tasks,
                SUM(
                    CASE
                        WHEN status = 'paused'
                            AND pause_reason ='auto_unread_threshold'
                        THEN 1 ELSE 0
                    END
                ) AS auto_paused_tasks,
                SUM(
                    CASE
                        WHEN status = 'paused'
                            AND pause_reason ='manual'
                        THEN 1 ELSE 0
                    END
                ) AS paused_tasks
            FROM swe_cron_jobs j
            WHERE {job_where}
            """,
            tuple(job_params),
        )
        return row or {}

    async def _fetch_previous_job_summary(
        self,
        db: Any,
        *,
        tenant_id: Optional[str],
        bbk_id: Optional[str],
        source_id: Optional[str],
        start_time: datetime,
    ) -> Dict[str, Any]:
        conditions = [
            "j.created_at < %s",
            "(j.deleted_at IS NULL OR j.deleted_at >= %s)",
            "j.status != 'deleted'",
        ]
        sql_params: List = [start_time, start_time]

        if tenant_id:
            conditions.append("j.tenant_id = %s")
            sql_params.append(tenant_id)

        if bbk_id:
            conditions.append("j.bbk_id = %s")
            sql_params.append(bbk_id)

        if source_id:
            conditions.append("j.source_id = %s")
            sql_params.append(source_id)

        row = await db.fetch_one(
            f"""
            SELECT COUNT(*) AS total_tasks
            FROM swe_cron_jobs j
            WHERE {' AND '.join(conditions)}
            """,
            tuple(sql_params),
        )
        return row or {}

    async def _fetch_overview_execution_summary(
        self,
        db: Any,
        exec_where: str,
        exec_params: List,
    ) -> Dict[str, Any]:
        row = await db.fetch_one(
            f"""
            SELECT
                COUNT(*) AS execution_count,
                SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END)
                    AS success_count,
                SUM(
                    CASE
                        WHEN e.status = 'error'
                        THEN 1 ELSE 0
                    END
                ) AS failure_count,
                COALESCE(
                    AVG(CASE WHEN e.status = 'success' THEN e.duration_ms END),
                    0
                ) AS avg_duration_ms
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {exec_where}
            """,
            tuple(exec_params),
        )
        return row or {}

    async def _fetch_previous_execution_summary(
        self,
        db: Any,
        *,
        tenant_id: Optional[str],
        bbk_id: Optional[str],
        source_id: Optional[str],
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        prev_start, prev_end = self._resolve_previous_period(start_time, end_time)
        prev_conditions, prev_params = self._build_overview_execution_conditions(
            tenant_id=tenant_id,
            bbk_id=bbk_id,
            source_id=source_id,
            start_time=prev_start,
            end_time=prev_end,
        )
        return await self._fetch_overview_execution_summary(
            db,
            " AND ".join(prev_conditions),
            prev_params,
        )

    def _resolve_previous_period(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> Tuple[datetime, datetime]:
        period_days = (end_time - start_time).days
        if period_days == 0:
            return start_time - timedelta(days=1), end_time - timedelta(days=1)
        return (
            start_time - timedelta(days=period_days),
            start_time - timedelta(seconds=1),
        )

    def _build_overview_metrics(
        self,
        job_summary: Dict[str, Any],
        prev_job_summary: Dict[str, Any],
        exec_summary: Dict[str, Any],
        prev_exec_summary: Dict[str, Any],
    ) -> List[CronOverviewMetricItem]:
        total_tasks = int(job_summary.get("total_tasks") or 0)
        prev_total_tasks = int(prev_job_summary.get("total_tasks") or 0)
        execution_count = int(exec_summary.get("execution_count") or 0)
        success_rate = self._calculate_success_rate(exec_summary)
        avg_duration_ms = float(exec_summary.get("avg_duration_ms") or 0)
        prev_success_rate = self._calculate_success_rate(prev_exec_summary)

        total_compare, total_trend = self._calc_total_delta(
            total_tasks,
            prev_total_tasks,
        )
        runs_compare, runs_trend = self._calc_compare(
            execution_count,
            int(prev_exec_summary.get("execution_count") or 0),
        )
        success_rate_compare, success_rate_trend = self._calc_compare(
            success_rate,
            prev_success_rate,
        )
        avg_cost_compare, avg_cost_trend = self._calc_compare(
            avg_duration_ms,
            float(prev_exec_summary.get("avg_duration_ms") or 0),
        )

        return [
            CronOverviewMetricItem(
                key="total",
                value=total_tasks,
                compare=total_compare,
                trend=total_trend,
            ),
            CronOverviewMetricItem(
                key="subscribed",
                value=int(job_summary.get("subscription_tasks") or 0),
            ),
            CronOverviewMetricItem(
                key="created",
                value=int(job_summary.get("manual_tasks") or 0),
            ),
            CronOverviewMetricItem(
                key="runs",
                value=execution_count,
                compare=runs_compare,
                trend=runs_trend,
            ),
            CronOverviewMetricItem(
                key="success_rate",
                value=success_rate,
                compare=success_rate_compare,
                trend=success_rate_trend,
            ),
            CronOverviewMetricItem(
                key="avg_cost",
                value=avg_duration_ms,
                compare=avg_cost_compare,
                trend=avg_cost_trend,
            ),
        ]

    def _calculate_success_rate(self, summary: Dict[str, Any]) -> float:
        success_count = int(summary.get("success_count") or 0)
        failure_count = int(summary.get("failure_count") or 0)
        total_count = success_count + failure_count
        return success_count / total_count * 100 if total_count else 0.0

    def _calc_total_delta(
        self,
        current: int,
        prev: int,
    ) -> Tuple[str, Optional[str]]:
        delta = current - prev
        if delta > 0:
            return f"{delta}", "up"
        if delta < 0:
            return f"{abs(delta)}", "down"
        return "", None

    def _calc_compare(
        self,
        current: float,
        prev: float,
    ) -> Tuple[str, Optional[str]]:
        if prev == 0:
            return "", None
        change = ((current - prev) / prev) * 100
        if change > 0:
            return f"+{change:.1f}%", "up"
        if change < 0:
            return f"{change:.1f}%", "down"
        return "0.0%", "up"

    def _build_task_status_distribution(
        self,
        job_summary: Dict[str, Any],
    ) -> List[CronOverviewDistributionItem]:
        return self._build_distribution(
            [
                ("生效中", int(job_summary.get("active_tasks") or 0)),
                (
                    "未读自动暂停",
                    int(job_summary.get("auto_paused_tasks") or 0),
                ),
                ("手动暂停", int(job_summary.get("paused_tasks") or 0)),
            ],
            {
                "生效中": "#2361EA",
                "未读自动暂停": "#F97212",
                "手动暂停": "#783AF1",
            },
        )

    async def _fetch_execution_result_distribution(
        self,
        db: Any,
        exec_where: str,
        exec_params: List,
    ) -> List[CronOverviewDistributionItem]:
        rows = await db.fetch_all(
            f"""
            SELECT
                CASE
                    WHEN e.status = 'success' THEN '成功'
                    WHEN e.status = 'error' THEN '失败'
                    WHEN e.status = 'cancelled' THEN '已取消/跳过'
                    ELSE e.status
                END AS name,
                COUNT(*) AS value
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {exec_where}
            GROUP BY e.status
            ORDER BY value DESC
            """,
            tuple(exec_params),
        )
        return self._build_distribution(
            self._distribution_pairs(rows),
            {
                "成功": "#13A146",
                "失败": "#f33f3d",
                "已取消/跳过": "#9b9db4",
            },
        )

    async def _fetch_read_status_distribution(
        self,
        db: Any,
        exec_where: str,
        exec_params: List,
    ) -> List[CronOverviewDistributionItem]:
        rows = await db.fetch_all(
            f"""
            SELECT
                CASE WHEN e.is_read = 1 THEN '已读' ELSE '未读' END AS name,
                COUNT(*) AS value
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {exec_where} AND e.status = 'success'
            GROUP BY e.is_read
            ORDER BY value DESC
            """,
            tuple(exec_params),
        )
        return self._build_distribution(
            self._distribution_pairs(rows),
            {"已读": "#2361EA", "未读": "#F97212"},
        )

    async def _fetch_failure_reason_distribution(
        self,
        db: Any,
        exec_where: str,
        exec_params: List,
    ) -> List[CronOverviewDistributionItem]:
        rows = await db.fetch_all(
            f"""
            SELECT
                CASE
                    WHEN e.error_message LIKE '%%channel not found%%'
                        THEN '渠道不存在'
                    WHEN e.error_message LIKE '%%cron auth user_info is expired%%'
                        THEN 'token过期'
                    WHEN e.error_message LIKE '%%Illegal Argument%%'
                        THEN '密文长度错误'
                    WHEN LOWER(e.error_message) LIKE '%%validation error for agentrequest%%'
                        THEN '智能体请求校验失败'
                    ELSE '其他'
                END AS name,
                COUNT(*) AS value
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {exec_where}
              AND e.status = 'error'
              AND j.status != 'deleted'
            GROUP BY 1
            ORDER BY value DESC, name ASC
            LIMIT 10
            """,
            tuple(exec_params),
        )
        return self._build_distribution(
            self._distribution_pairs(rows),
            {
                "渠道不存在": "#ef4444",
                "token过期": "#f97316",
                "密文长度错误": "#eab308",
                "智能体请求校验失败": "#8b5cf6",
                "其他": "#64748b",
            },
        )

    async def _fetch_branch_task_distribution(
        self,
        db: Any,
        job_where: str,
        job_params: List,
    ) -> List[CronOverviewDistributionItem]:
        rows = await db.fetch_all(
            f"""
            SELECT COALESCE(NULLIF(j.bbk_id, ''), 'unknown') AS name,
                   COUNT(*) AS value
            FROM swe_cron_jobs j
            WHERE {job_where} 
                AND j.status IN ('active', 'paused')
            GROUP BY j.bbk_id
            ORDER BY value DESC, name ASC
            """,
            tuple(job_params),
        )
        return self._build_distribution(
            [
                (
                    self._format_branch_name(row.get("name") or "unknown"),
                    int(row.get("value") or 0),
                )
                for row in rows
            ],
            {"unknown": "#94a3b8"},
        )

    async def _fetch_branch_execution_distribution(
        self,
        db: Any,
        exec_where: str,
        exec_params: List,
    ) -> List[CronOverviewBranchExecutionItem]:
        rows = await db.fetch_all(
            f"""
            SELECT
                COALESCE(NULLIF(j.bbk_id, ''), 'unknown') AS name,
                SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END)
                    AS success,
                SUM(
                    CASE
                        WHEN e.status = 'error'
                        THEN 1 ELSE 0
                    END
                ) AS failed,
                SUM(CASE WHEN e.status = 'skipped' THEN 1 ELSE 0 END)
                    AS skipped
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {exec_where}
            GROUP BY j.bbk_id
            ORDER BY (success + failed + skipped) DESC, name ASC
            """,
            tuple(exec_params),
        )
        return [
            CronOverviewBranchExecutionItem(
                name=self._format_branch_name(row.get("name") or "unknown"),
                success=int(row.get("success") or 0),
                failed=int(row.get("failed") or 0),
                skipped=int(row.get("skipped") or 0),
            )
            for row in rows
        ]

    async def _fetch_branch_read_distribution(
        self,
        db: Any,
        exec_where: str,
        exec_params: List,
    ) -> List[CronOverviewBranchReadItem]:
        rows = await db.fetch_all(
            f"""
            SELECT
                COALESCE(NULLIF(j.bbk_id, ''), 'unknown') AS name,
                SUM(CASE WHEN e.is_read = 1 THEN 1 ELSE 0 END) AS read_count,
                SUM(CASE WHEN e.is_read = 0 THEN 1 ELSE 0 END) AS unread_count
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {exec_where} AND e.status = 'success'
            GROUP BY j.bbk_id
            ORDER BY (read_count + unread_count) DESC, name ASC
            """,
            tuple(exec_params),
        )
        return [
            CronOverviewBranchReadItem(
                name=self._format_branch_name(row.get("name") or "unknown"),
                read=int(row.get("read_count") or 0),
                unread=int(row.get("unread_count") or 0),
            )
            for row in rows
        ]

    def _format_branch_name(self, bbk_id: Any) -> str:
        normalized_bbk_id = str(bbk_id or "").strip()
        if normalized_bbk_id == "unknown":
            return "unknown"
        return get_bbk_name_by_id(normalized_bbk_id) or normalized_bbk_id

    def _distribution_pairs(self, rows: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
        return [
            (row.get("name") or "unknown", int(row.get("value") or 0))
            for row in rows
        ]

    async def get_subscription_overview(
        self,
        *,
        keyword: Optional[str] = None,
        tenant_id: Optional[str] = None,
        bbk_id: Optional[str] = None,
        source_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> PaginatedResponse[SubscriptionOverviewItem]:
        """按订阅任务分组统计当天概览数据。"""
        db = get_db_connection()
        start_time, end_time = self._resolve_today_range(start_time, end_time)
        conditions, sql_params = self._build_subscription_conditions(
            keyword=keyword,
            tenant_id=tenant_id,
            bbk_id=bbk_id,
            source_id=source_id,
        )
        where_clause = " AND ".join(conditions)
        group_key = "COALESCE(NULLIF(j.subscription_key, ''), CONCAT('job:', j.id))"

        count_sql = f"""
            SELECT COUNT(*) as count
            FROM (
                SELECT {group_key} AS subscription_group
                FROM swe_cron_jobs j
                WHERE {where_clause}
                GROUP BY subscription_group
            ) grouped
        """
        count_result = await db.fetch_one(count_sql, tuple(sql_params))
        total = count_result.get("count", 0) if count_result else 0

        offset = (page - 1) * page_size
        latest_execution_sql = """
            SELECT e.*
            FROM swe_cron_executions e
            INNER JOIN (
                SELECT job_id, MAX(actual_time) AS latest_actual_time
                FROM swe_cron_executions
                WHERE actual_time >= %s AND actual_time <= %s
                GROUP BY job_id
            ) latest
                ON latest.job_id = e.job_id
                AND latest.latest_actual_time = e.actual_time
        """
        query_sql = f"""
            SELECT
                {group_key} AS subscription_key,
                MAX(j.name) AS task_name,
                COUNT(*) AS total_task_count,
                COUNT(DISTINCT NULLIF(j.creator_user_id, '')) AS subscriber_count,
                SUM(CASE WHEN le.status = 'running' THEN 1 ELSE 0 END)
                    AS running_task_count,
                SUM(
                    CASE
                        WHEN le.job_id IS NULL
                            AND j.enabled = 1
                            AND j.status = 'active'
                        THEN 1 ELSE 0
                    END
                ) AS pending_task_count,
                SUM(CASE WHEN le.status = 'success' THEN 1 ELSE 0 END)
                    AS executed_task_count,
                SUM(
                    CASE
                        WHEN le.status IN ('error', 'timeout', 'cancelled')
                        THEN 1 ELSE 0
                    END
                ) AS failed_task_count,
                COALESCE(
                    AVG(CASE WHEN le.status = 'success' THEN le.duration_ms END),
                    0
                ) AS avg_duration_ms,
                SUM(CASE WHEN le.status = 'success' THEN 1 ELSE 0 END)
                    AS success_count,
                SUM(
                    CASE
                        WHEN le.status IN ('success', 'error', 'timeout', 'cancelled')
                        THEN 1 ELSE 0
                    END
                ) AS completed_count
            FROM swe_cron_jobs j
            LEFT JOIN ({latest_execution_sql}) le ON le.job_id = j.id
            WHERE {where_clause}
            GROUP BY subscription_key
            ORDER BY total_task_count DESC, task_name ASC
            LIMIT %s OFFSET %s
        """
        rows = await db.fetch_all(
            query_sql,
            (start_time, end_time, *sql_params, page_size, offset),
        )

        items = []
        for row in rows:
            completed_count = int(row.get("completed_count") or 0)
            success_count = int(row.get("success_count") or 0)
            success_rate = (
                success_count / completed_count if completed_count else 0.0
            )
            items.append(
                SubscriptionOverviewItem(
                    subscription_key=row.get("subscription_key") or "",
                    task_name=row.get("task_name") or "",
                    subscriber_count=int(row.get("subscriber_count") or 0),
                    total_task_count=int(row.get("total_task_count") or 0),
                    running_task_count=int(row.get("running_task_count") or 0),
                    pending_task_count=int(row.get("pending_task_count") or 0),
                    executed_task_count=int(row.get("executed_task_count") or 0),
                    failed_task_count=int(row.get("failed_task_count") or 0),
                    avg_duration_ms=float(row.get("avg_duration_ms") or 0),
                    success_rate=success_rate,
                ),
            )

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_subscription_details(
        self,
        subscription_key: str,
        *,
        tenant_id: Optional[str] = None,
        bbk_id: Optional[str] = None,
        source_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> PaginatedResponse[SubscriptionDetailItem]:
        """查询订阅任务详情弹窗数据。"""
        db = get_db_connection()
        start_time, end_time = self._resolve_today_range(start_time, end_time)
        conditions, sql_params = self._build_subscription_conditions(
            tenant_id=tenant_id,
            bbk_id=bbk_id,
            source_id=source_id,
        )
        conditions.append("j.subscription_key = %s")
        sql_params.append(subscription_key)
        where_clause = " AND ".join(conditions)

        count_sql = f"""
            SELECT COUNT(*) as count
            FROM swe_cron_jobs j
            WHERE {where_clause}
        """
        count_result = await db.fetch_one(count_sql, tuple(sql_params))
        total = count_result.get("count", 0) if count_result else 0

        offset = (page - 1) * page_size
        latest_execution_sql = """
            SELECT e.*
            FROM swe_cron_executions e
            INNER JOIN (
                SELECT job_id, MAX(actual_time) AS latest_actual_time
                FROM swe_cron_executions
                WHERE actual_time >= %s AND actual_time <= %s
                GROUP BY job_id
            ) latest
                ON latest.job_id = e.job_id
                AND latest.latest_actual_time = e.actual_time
        """
        query_sql = f"""
            SELECT
                j.id AS job_id,
                j.creator_user_id AS subscriber_id,
                j.tenant_name AS subscriber_name,
                j.bbk_id,
                j.enabled,
                CASE WHEN le.job_id IS NULL THEN 'pending' ELSE 'executed' END
                    AS execution_status,
                le.actual_time AS execution_time
            FROM swe_cron_jobs j
            LEFT JOIN ({latest_execution_sql}) le ON le.job_id = j.id
            WHERE {where_clause}
            ORDER BY j.created_at DESC
            LIMIT %s OFFSET %s
        """
        rows = await db.fetch_all(
            query_sql,
            (start_time, end_time, *sql_params, page_size, offset),
        )
        items = [
            SubscriptionDetailItem(
                job_id=row.get("job_id") or "",
                subscriber_id=row.get("subscriber_id") or "",
                subscriber_name=row.get("subscriber_name") or "",
                bbk_id=row.get("bbk_id") or "",
                enabled=bool(row.get("enabled")),
                execution_status=row.get("execution_status") or "pending",
                execution_time=row.get("execution_time"),
            )
            for row in rows
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def _resolve_today_range(
        self,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> Tuple[datetime, datetime]:
        """未传时间范围时默认使用北京时间当天。"""
        if start_time and end_time:
            return start_time, end_time
        today_start = datetime.now(BEIJING_TZ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        today_end = today_start.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        )
        return today_start - timedelta(hours=8), today_end - timedelta(hours=8)

    def _build_distribution(
        self,
        pairs: List[Tuple[str, int]],
        color_map: Optional[Dict[str, str]] = None,
    ) -> List[CronOverviewDistributionItem]:
        """Build chart items with percentages."""
        total = sum(value for _, value in pairs)
        items = []
        for name, value in pairs:
            percent = (value / total * 100) if total else 0.0
            color = color_map.get(name) if color_map else None
            items.append(
                CronOverviewDistributionItem(
                    name=name,
                    value=value,
                    percent=round(percent, 2),
                    color=color,
                ),
            )
        return items

    def _build_overview_job_conditions(
        self,
        *,
        tenant_id: Optional[str] = None,
        bbk_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Tuple[List[str], List]:
        """Build filters for swe_cron_jobs overview queries."""
        conditions = ["j.deleted_at IS NULL", "j.status != 'deleted'"]
        sql_params: List = []
        if tenant_id:
            conditions.append("j.tenant_id = %s")
            sql_params.append(tenant_id)
        if bbk_id:
            conditions.append("j.bbk_id = %s")
            sql_params.append(bbk_id)
        if source_id:
            conditions.append("j.source_id = %s")
            sql_params.append(source_id)
        return conditions, sql_params

    def _build_overview_execution_conditions(
        self,
        *,
        tenant_id: Optional[str] = None,
        bbk_id: Optional[str] = None,
        source_id: Optional[str] = None,
        start_time: datetime,
        end_time: datetime,
    ) -> Tuple[List[str], List]:
        """Build filters for swe_cron_executions overview queries."""
        conditions = [
            "e.actual_time >= %s",
            "e.actual_time <= %s",
            "j.status != 'deleted'",
        ]
        sql_params: List = [start_time, end_time]
        if tenant_id:
            conditions.append("e.tenant_id = %s")
            sql_params.append(tenant_id)
        if bbk_id:
            conditions.append("j.bbk_id = %s")
            sql_params.append(bbk_id)
        if source_id:
            conditions.append("j.source_id = %s")
            sql_params.append(source_id)
        return conditions, sql_params

    def _build_subscription_conditions(
        self,
        *,
        keyword: Optional[str] = None,
        tenant_id: Optional[str] = None,
        bbk_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Tuple[List[str], List]:
        """构建订阅任务查询条件。"""
        conditions = ["j.deleted_at IS NULL", "j.job_origin = 'subscription'"]
        sql_params: List = []
        if keyword:
            conditions.append(
                "j.name LIKE %s",
            )
            keyword_like = f"%{keyword}%"
            sql_params.append(keyword_like)
        if tenant_id:
            conditions.append("j.tenant_id = %s")
            sql_params.append(tenant_id)
        if bbk_id:
            conditions.append("j.bbk_id = %s")
            sql_params.append(bbk_id)
        if source_id:
            conditions.append("j.source_id = %s")
            sql_params.append(source_id)
        return conditions, sql_params

    async def mark_job_as_read(
        self,
        job_id: str,
        source_id: Optional[str] = None,
    ) -> int:
        """标记任务及其历史执行记录为已读。

        将指定任务的所有成功执行的未读记录标记为已读，
        同时更新该任务之前所有未读的成功执行记录。

        Args:
            job_id: 任务ID
            source_id: Source ID filter

        Returns:
            更新的记录数量
        """
        db = get_db_connection()
        # 数据库存储的是 naive datetime（东八区时间），去掉时区信息
        now = datetime.now(BEIJING_TZ).replace(tzinfo=None)

        # 更新该任务所有成功的未读执行记录
        update_sql = """
            UPDATE swe_cron_executions e
            SET is_read = TRUE, read_at = %s
            WHERE e.job_id = %s
            AND e.status = 'success'
            AND e.is_read = FALSE
        """
        source_filter = source_id or ""
        logger.info(f"[mark_executions_read] 开始标记已读, job_id={job_id}")
        logger.debug(f"[mark_executions_read] SQL: {update_sql}")

        result = await db.execute(update_sql, (now, job_id))
        logger.info(f"[mark_executions_read] UPDATE执行完成, job_id={job_id}")
        # 获取更新的记录数量
        count_sql = """
            SELECT COUNT(*) as count
            FROM swe_cron_executions e
            WHERE e.job_id = %s
            AND e.status = 'success'
            AND e.is_read = TRUE
        """
        result = await db.fetch_one(count_sql, (job_id, source_filter, source_filter))
        return result.get("count", 0) if result else 0


    async def get_unread_count(
        self,
        tenant_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> UnreadCountResponse:
        """获取未读任务数量统计。

        按任务分组统计未读的成功执行记录数量，
        用于前端展示未读提醒。

        Args:
            tenant_id: 租户ID筛选（可选）
            source_id: Source ID filter

        Returns:
            包含各任务未读数量的字典
        """
        db = get_db_connection()

        conditions = ["e.status = 'success'", "e.is_read = FALSE"]
        sql_params: List = []

        if tenant_id:
            conditions.append("e.tenant_id = %s")
            sql_params.append(tenant_id)

        if source_id:
            conditions.append("j.source_id = %s")
            sql_params.append(source_id)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT e.job_id, e.job_name, COUNT(*) as unread_count
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE {where_clause}
            GROUP BY e.job_id, e.job_name
            ORDER BY unread_count DESC
        """
        rows = await db.fetch_all(
            sql,
            tuple(sql_params) if sql_params else None,
        )

        return UnreadCountResponse(
            items=[
                {
                    "job_id": row["job_id"],
                    "job_name": row["job_name"] or row["job_id"],
                    "unread_count": row["unread_count"],
                }
                for row in rows
            ],
            total_unread=sum(row["unread_count"] for row in rows),
        )


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
