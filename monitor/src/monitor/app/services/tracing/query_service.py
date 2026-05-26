# -*- coding: utf-8 -*-
"""Tracing query service for operational dashboard."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from ...database import get_db_connection, DatabaseConnection
from ....utils.bbk import get_bbk_name_by_id
from ...models.tracing import (
    EventType,
    ModelUsage,
    MCPToolUsage,
    MCPServerUsage,
    MCPSummary,
    OverviewStats,
    SessionListItem,
    SessionStats,
    SkillCallTimeline,
    SkillUsage,
    Span,
    TimelineEvent,
    ToolCallInSkill,
    ToolUsage,
    Trace,
    TraceDetail,
    TraceFeedback,
    TraceDetailWithTimeline,
    TraceListItem,
    TraceStatus,
    UserListItem,
    UserMessageItem,
    UserStats,
    TaskStatusSummary,
    DepthSummary,
)

logger = logging.getLogger(__name__)

# 需要从统计中排除的 source_id（测试平台等）
EXCLUDED_SOURCE_IDS = ["default"]

LATEST_FEEDBACK_JOIN_SQL = """
    LEFT JOIN (
        SELECT rf1.*
        FROM swe_response_feedback rf1
        INNER JOIN (
            SELECT trace_id, source_id, MAX(id) AS max_id
            FROM swe_response_feedback
            WHERE trace_id IS NOT NULL
            GROUP BY trace_id, source_id
        ) latest ON latest.max_id = rf1.id
    ) rf ON rf.trace_id COLLATE utf8mb4_unicode_ci = t.trace_id COLLATE utf8mb4_unicode_ci
        AND rf.source_id COLLATE utf8mb4_unicode_ci <=> t.source_id COLLATE utf8mb4_unicode_ci
"""

FEEDBACK_SELECT_SQL = """
    rf.id as feedback_id,
    rf.source_id as feedback_source_id,
    rf.feedback_user_name as feedback_user_name,
    rf.feedback_user_sap as feedback_user_sap,
    rf.feedback_branch as feedback_branch,
    rf.feedback_sub_branch as feedback_sub_branch,
    rf.feedback_position as feedback_position,
    rf.cron_task_name as feedback_cron_task_name,
    rf.cron_task_id as feedback_cron_task_id,
    rf.response_id as feedback_response_id,
    rf.trace_id as feedback_trace_id,
    rf.chat_id as feedback_chat_id,
    rf.session_id as feedback_session_id,
    rf.feedback_options as feedback_options,
    rf.feedback_content as feedback_content,
    rf.created_at as feedback_created_at,
    rf.updated_at as feedback_updated_at
"""


def build_bbk_in_filter(bbk_ids: Optional[str]) -> tuple[str, list[str]]:
    """构建 bbk IN 过滤条件，支持逗号分隔的多值.

    Args:
        bbk_ids: 逗号分隔的 bbk_id 字符串，如 "100,200,201"

    Returns:
        (filter_sql, params) - 如 " AND bbk_id IN (%s, %s, %s)", ["100", "200", "201"]
        无值时返回 ("", [])
    """
    if not bbk_ids:
        return "", []
    ids = [id.strip() for id in bbk_ids.split(",") if id.strip()]
    if not ids:
        return "", []
    placeholders = ", ".join(["%s"] * len(ids))
    return f" AND bbk_id IN ({placeholders})", ids


def _loads_feedback_options(raw: Any) -> list[str]:
    """解析反馈快捷选项，兼容数据库 JSON 字符串和列表。"""
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _row_to_feedback(row: dict[str, Any]) -> Optional[TraceFeedback]:
    """把查询结果中的反馈字段转换为 TraceFeedback。"""
    feedback_id = row.get("feedback_id") or row.get("id")
    if feedback_id is None:
        return None

    return TraceFeedback(
        id=int(feedback_id),
        source_id=row.get("feedback_source_id") or row.get("source_id"),
        feedback_user_name=row.get("feedback_user_name"),
        feedback_user_sap=row.get("feedback_user_sap"),
        feedback_branch=row.get("feedback_branch"),
        feedback_sub_branch=row.get("feedback_sub_branch"),
        feedback_position=row.get("feedback_position"),
        cron_task_name=row.get("feedback_cron_task_name")
        or row.get("cron_task_name"),
        cron_task_id=row.get("feedback_cron_task_id")
        or row.get("cron_task_id"),
        response_id=row.get("feedback_response_id") or row.get("response_id"),
        trace_id=row.get("feedback_trace_id") or row.get("trace_id"),
        chat_id=row.get("feedback_chat_id") or row.get("chat_id"),
        session_id=row.get("feedback_session_id") or row.get("session_id"),
        feedback_options=_loads_feedback_options(
            row.get("feedback_options"),
        ),
        feedback_content=row.get("feedback_content") or "",
        created_at=row.get("feedback_created_at") or row.get("created_at"),
        updated_at=row.get("feedback_updated_at") or row.get("updated_at"),
    )


def build_cron_bbk_in_filter(bbk_ids: Optional[str]) -> tuple[str, list[str]]:
    """构建定时任务表 bbk IN 过滤条件，支持逗号分隔的多值.

    Args:
        bbk_ids: 逗号分隔的 bbk_id 字符串，如 "100,200,201"

    Returns:
        (filter_sql, params) - 如 " AND j.bbk_id IN (%s, %s, %s)", ["100", "200", "201"]
        无值时返回 ("", [])
    """
    if not bbk_ids:
        return "", []
    ids = [id.strip() for id in bbk_ids.split(",") if id.strip()]
    if not ids:
        return "", []
    placeholders = ", ".join(["%s"] * len(ids))
    return f" AND j.bbk_id IN ({placeholders})", ids


class TracingQueryService:
    """运营看板查询服务."""

    def __init__(self, db: DatabaseConnection):
        """初始化查询服务.

        Args:
            db: 数据库连接实例
        """
        self._db = db

    @classmethod
    def get_instance(cls) -> "TracingQueryService":
        """获取服务实例（使用全局数据库连接）."""
        db = get_db_connection()
        return cls(db)

    # ===== 运营概览 =====

    async def get_overview_stats(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> OverviewStats:
        """获取运营概览统计."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        # 并行获取当前周期各项统计数据
        (
            total_users,
            (online_users, online_user_ids),
            token_row,
            model_distribution,
            top_tools,
            top_skills,
            (top_mcp_tools, mcp_servers),
            branch_breakdown,
            total_skill_calls,
        ) = await self._fetch_overview_data(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        )

        return self._build_overview_stats(
            total_users=total_users,
            online_users=online_users,
            online_user_ids=online_user_ids,
            model_distribution=model_distribution,
            token_row=token_row,
            top_tools=top_tools,
            top_skills=top_skills,
            top_mcp_tools=top_mcp_tools,
            mcp_servers=mcp_servers,
            branch_breakdown=branch_breakdown,
            total_skill_calls=total_skill_calls,
        )

    async def _fetch_overview_data(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list:
        """并行获取运营概览的各项数据."""
        return await asyncio.gather(
            self._get_total_users(source_id, start_date, end_date, bbk_ids),
            self._get_online_users(source_id, bbk_ids),
            self._get_token_stats(source_id, start_date, end_date, bbk_ids),
            self._get_model_distribution(
                source_id,
                start_date,
                end_date,
                bbk_ids,
            ),
            self._get_top_tools(source_id, start_date, end_date, bbk_ids),
            self._get_top_skills(source_id, start_date, end_date, bbk_ids),
            self._get_mcp_stats(source_id, start_date, end_date, bbk_ids),
            self._get_branch_breakdown(
                source_id,
                start_date,
                end_date,
                bbk_ids,
            ),
            self._get_total_skill_calls(
                source_id,
                start_date,
                end_date,
                bbk_ids,
            ),
        )

    def _build_overview_stats(
        self,
        total_users: int,
        online_users: int,
        online_user_ids: list[str],
        token_row: Optional[dict],
        model_distribution: list,
        top_tools: list,
        top_skills: list,
        top_mcp_tools: list,
        mcp_servers: list,
        branch_breakdown: Any,
        total_skill_calls: int = 0,
    ) -> OverviewStats:
        """构建运营概览统计对象."""
        return OverviewStats(
            online_users=online_users,
            online_user_ids=online_user_ids,
            total_users=total_users,
            model_distribution=model_distribution,
            total_tokens=token_row["total_tokens"] or 0 if token_row else 0,
            input_tokens=token_row["input_tokens"] or 0 if token_row else 0,
            output_tokens=token_row["output_tokens"] or 0 if token_row else 0,
            total_sessions=(
                token_row["total_sessions"] or 0 if token_row else 0
            ),
            total_conversations=(
                token_row["total_traces"] or 0 if token_row else 0
            ),
            total_skill_calls=total_skill_calls,
            avg_duration_ms=self._extract_avg_duration(token_row),
            top_tools=top_tools,
            top_skills=top_skills,
            top_mcp_tools=top_mcp_tools,
            mcp_servers=mcp_servers,
            daily_trend=[],
            branch_breakdown=branch_breakdown,
        )

    def _extract_avg_duration(self, token_row: Optional[dict]) -> int:
        """从 token 统计行中提取平均时长."""
        if token_row and token_row.get("avg_duration"):
            return int(token_row["avg_duration"] or 0)
        return 0

    async def _get_branch_breakdown(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> Any:
        """获取分行级别统计数据."""
        from ...models.tracing import (
            BranchMetricItem,
            OverviewBranchBreakdown,
        )

        # 构建查询条件 - 使用辅助函数处理多值过滤
        bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            trace_where = f"""
                start_time >= %s AND start_time < %s
                AND source_id NOT IN ({exclude_placeholders})
                AND user_id != 'default'
                AND bbk_id IS NOT NULL AND bbk_id != ''{bbk_filter_sql}
            """
            trace_params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_params,
            )
            span_where = f"""
                start_time >= %s AND start_time < %s
                AND source_id NOT IN ({exclude_placeholders})
                AND user_id != 'default'
                AND bbk_id IS NOT NULL AND bbk_id != ''{bbk_filter_sql}
            """
            span_params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_params,
            )
        else:
            trace_where = f"""
                source_id = %s AND start_time >= %s AND start_time < %s
                AND user_id != 'default'
                AND bbk_id IS NOT NULL AND bbk_id != ''{bbk_filter_sql}
            """
            trace_params = (source_id, start_date, end_date, *bbk_params)
            span_where = f"""
                source_id = %s AND start_time >= %s AND start_time < %s
                AND user_id != 'default'
                AND bbk_id IS NOT NULL AND bbk_id != ''{bbk_filter_sql}
            """
            span_params = (source_id, start_date, end_date, *bbk_params)

        # 各项分行统计查询
        users_query = f"""
            SELECT bbk_id, COUNT(DISTINCT user_id) AS value
            FROM swe_tracing_traces
            WHERE {trace_where}
            GROUP BY bbk_id
            ORDER BY value DESC
            LIMIT 5
        """
        conversations_query = f"""
            SELECT bbk_id, COUNT(*) AS value
            FROM swe_tracing_traces
            WHERE {trace_where}
            GROUP BY bbk_id
            ORDER BY value DESC
            LIMIT 5
        """
        sessions_query = f"""
            SELECT bbk_id, COUNT(DISTINCT session_id) AS value
            FROM swe_tracing_traces
            WHERE {trace_where}
            GROUP BY bbk_id
            ORDER BY value DESC
            LIMIT 5
        """
        tokens_query = f"""
            SELECT bbk_id, COALESCE(SUM(total_tokens), 0) AS value
            FROM swe_tracing_traces
            WHERE {trace_where}
            GROUP BY bbk_id
            ORDER BY value DESC
            LIMIT 5
        """
        skills_query = f"""
            SELECT bbk_id, COUNT(*) AS value
            FROM swe_tracing_spans
            WHERE {span_where}
              AND event_type = 'skill_invocation'
              AND skill_name IS NOT NULL
            GROUP BY bbk_id
            ORDER BY value DESC
            LIMIT 5
        """

        # 定时任务分行统计查询
        cron_bbk_filter_sql, cron_bbk_params = build_cron_bbk_in_filter(
            bbk_ids,
        )
        cron_exclude_placeholders = ", ".join(
            ["%s"] * len(EXCLUDED_SOURCE_IDS),
        )
        if source_id == "all":
            cron_query = f"""
                SELECT j.bbk_id, COUNT(*) AS value
                FROM swe_cron_executions e
                INNER JOIN swe_cron_jobs j ON e.job_id = j.id
                WHERE e.actual_time >= %s AND e.actual_time < %s
                  AND j.status != 'deleted'
                  AND j.deleted_at IS NULL
                  AND j.source_id NOT IN ({cron_exclude_placeholders})
                  AND j.tenant_id != 'default'
                  AND j.bbk_id IS NOT NULL AND j.bbk_id != ''
                  {cron_bbk_filter_sql}
                GROUP BY j.bbk_id
                ORDER BY value DESC
                LIMIT 5
            """
            cron_params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *cron_bbk_params,
            )
        else:
            cron_query = f"""
                SELECT j.bbk_id, COUNT(*) AS value
                FROM swe_cron_executions e
                INNER JOIN swe_cron_jobs j ON e.job_id = j.id
                WHERE e.actual_time >= %s AND e.actual_time < %s
                  AND j.status != 'deleted'
                  AND j.deleted_at IS NULL
                  AND j.tenant_id != 'default'
                  AND j.bbk_id IS NOT NULL AND j.bbk_id != ''
                  AND j.source_id = %s
                  {cron_bbk_filter_sql}
                GROUP BY j.bbk_id
                ORDER BY value DESC
                LIMIT 5
            """
            cron_params = (start_date, end_date, source_id, *cron_bbk_params)

        # 执行查询
        users_rows = await self._db.fetch_all(users_query, trace_params)
        conversations_rows = await self._db.fetch_all(
            conversations_query,
            trace_params,
        )
        sessions_rows = await self._db.fetch_all(sessions_query, trace_params)
        tokens_rows = await self._db.fetch_all(tokens_query, trace_params)
        skills_rows = await self._db.fetch_all(skills_query, span_params)
        cron_rows = await self._db.fetch_all(cron_query, cron_params)

        def build_branch_items(rows: list) -> list[BranchMetricItem]:
            total = sum(float(r.get("value") or 0) for r in rows)
            result = []
            for row in rows:
                value = float(row.get("value") or 0)
                percent = (value / total * 100) if total > 0 else 0
                bbk_id = row.get("bbk_id") or ""
                result.append(
                    BranchMetricItem(
                        bbk_id=bbk_id,
                        bbk_name=get_bbk_name_by_id(bbk_id) or bbk_id,
                        value=value,
                        percent=percent,
                    ),
                )
            return result

        return OverviewBranchBreakdown(
            users=build_branch_items(users_rows),
            conversations=build_branch_items(conversations_rows),
            sessions=build_branch_items(sessions_rows),
            tokens=build_branch_items(tokens_rows),
            skills=build_branch_items(skills_rows),
            cron_tasks=build_branch_items(cron_rows),
        )

    async def get_growth_stats(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        time_range: str = "day",
        bbk_ids: Optional[str] = None,
    ) -> dict[str, Any]:
        """获取运营看板核心指标的环比结果。

        统计范围：
        - 主事实表为 `swe_tracing_traces`，用于调用量、Token、会话数、
          活跃用户数等核心规模指标。
        - 技能调用量来自 `swe_tracing_spans`，仅统计
          `event_type='skill_invocation'` 且 `skill_name` 非空的记录。
        - 定时任务执行量来自 `swe_cron_executions` 与 `swe_cron_jobs` 的
          关联结果，口径为有效任务的执行记录数。
        - `source_id='all'` 时汇总全部正式平台，并排除
          `EXCLUDED_SOURCE_IDS`；指定 `source_id` 时仅统计单个平台。
        - `bbk_ids` 为分行并集过滤条件，作用于 trace、span 与 cron
          相关统计。

        对比周期：
        - 当前周期由调用方传入 `start_date`、`end_date` 定义。
        - 上一周期的回溯长度由 `time_range` 决定：`day/week/month`
          分别对应 1/7/30 天，`custom` 对应当前时间窗的自然日差值。
        - 上一周期的结束边界与当前周期起点对齐，避免两个周期发生重叠。

        返回字段口径：
        - `callsGrowth`：调用量环比，口径为 trace 记录数。
        - `tokensGrowth`：资源消耗环比，口径为 `total_tokens` 汇总值。
        - `sessionGrowth`：会话数环比，口径为 `session_id` 去重数。
        - `userGrowth`：活跃用户数环比，口径为 `user_id` 去重数。
        - `skillGrowth`：技能调用次数环比，口径为技能调用 span 数。
        - `cronGrowth`：定时任务执行次数环比，口径为 cron 执行记录数。
        - `avgRoundsGrowth`：单次会话平均轮数环比，口径为 `calls/sessions`。
        - `multiRoundRatioGrowth`：多轮会话占比环比，口径为大于 3 轮
          会话的占比。
        - `avgDurationGrowth`：平均对话时长环比，口径为秒。
        - `avgSessionsPerUserGrowth`：人均会话数环比，口径为
          `sessions/users`。
        """
        # pylint: disable=too-many-statements
        # 环比回溯长度与看板筛选粒度保持一致，确保上一周期和当前周期
        # 在展示层具备可直接比较的业务含义。
        period_days = 1
        if time_range == "week":
            period_days = 7
        elif time_range == "month":
            period_days = 30
        elif time_range == "custom":
            period_days = (end_date - start_date).days

        prev_start = start_date - timedelta(days=period_days)
        # 使用 start_date 作为上一周期的结束时间，配合 SQL 的 < 比较
        # 避免使用 timedelta(seconds=1) 造成的时间间隙问题
        prev_end = start_date

        # 分行筛选口径在所有子指标上保持一致，避免不同卡片的环比基线不一致。
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)

        async def get_stats(
            s: datetime,
            e: datetime,
            is_prev: bool = False,
        ) -> dict:
            # 基础规模指标统一从 trace 主表读取，确保调用量、Token、
            # 会话数、活跃用户数共享同一事实口径。
            # 对于上一周期，使用 < 比较；对于当前周期，使用 <= 比较
            time_compare = "<" if is_prev else "<="
            if source_id == "all":
                exclude_placeholders = ", ".join(
                    ["%s"] * len(EXCLUDED_SOURCE_IDS),
                )
                query = f"""
                    SELECT
                        COUNT(*) as calls,
                        COALESCE(SUM(total_tokens), 0) as tokens,
                        COUNT(DISTINCT session_id) as sessions,
                        COUNT(DISTINCT user_id) as users
                    FROM swe_tracing_traces
                    WHERE start_time >= %s AND start_time {time_compare} %s
                      AND source_id NOT IN ({exclude_placeholders})
                      AND user_id != 'default'{bbk_filter_sql}
                """
                params = (s, e, *EXCLUDED_SOURCE_IDS, *bbk_filter_params)
                row = await self._db.fetch_one(query, params)
            else:
                query = f"""
                    SELECT
                        COUNT(*) as calls,
                        COALESCE(SUM(total_tokens), 0) as tokens,
                        COUNT(DISTINCT session_id) as sessions,
                        COUNT(DISTINCT user_id) as users
                    FROM swe_tracing_traces
                    WHERE source_id = %s AND start_time >= %s AND start_time {time_compare} %s
                      AND user_id != 'default'{bbk_filter_sql}
                """
                params = (source_id, s, e, *bbk_filter_params)
                row = await self._db.fetch_one(query, params)

            if row is None:
                return {
                    "calls": 0,
                    "tokens": 0.0,
                    "sessions": 0,
                    "users": 0,
                }
            return {
                "calls": row["calls"] or 0,
                "tokens": float(row["tokens"] or 0),
                "sessions": row["sessions"] or 0,
                "users": row["users"] or 0,
            }

        async def get_skill_calls(
            s: datetime,
            e: datetime,
            is_prev: bool = False,
        ) -> int:
            # 技能调用量单独取 span 表口径，避免把普通 trace 误计为技能调用。
            time_compare = "<" if is_prev else "<="
            if source_id == "all":
                exclude_placeholders = ", ".join(
                    ["%s"] * len(EXCLUDED_SOURCE_IDS),
                )
                query = f"""
                    SELECT COUNT(*) as total
                    FROM swe_tracing_spans
                    WHERE start_time >= %s AND start_time {time_compare} %s
                      AND source_id NOT IN ({exclude_placeholders})
                      AND user_id != 'default'
                      AND event_type = 'skill_invocation'
                      AND skill_name IS NOT NULL{bbk_filter_sql}
                """
                params = (s, e, *EXCLUDED_SOURCE_IDS, *bbk_filter_params)
                row = await self._db.fetch_one(query, params)
            else:
                query = f"""
                    SELECT COUNT(*) as total
                    FROM swe_tracing_spans
                    WHERE source_id = %s AND start_time >= %s AND start_time {time_compare} %s
                      AND user_id != 'default'
                      AND event_type = 'skill_invocation'
                      AND skill_name IS NOT NULL{bbk_filter_sql}
                """
                params = (source_id, s, e, *bbk_filter_params)
                row = await self._db.fetch_one(query, params)
            return int((row or {}).get("total") or 0)

        async def get_cron_tasks_count(
            s: datetime,
            e: datetime,
            is_prev: bool = False,
        ) -> int:
            """查询定时任务执行次数（cron_executions 表）.

            统计的是有效任务的执行记录数，不是任务定义数；删除态任务、
            默认租户任务和被排除平台的数据均不纳入口径。
            """
            time_compare = "<" if is_prev else "<="
            bbk_filter_sql, bbk_filter_params = build_cron_bbk_in_filter(
                bbk_ids,
            )
            cron_exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            if source_id == "all":
                query = f"""
                    SELECT COUNT(*) as total
                    FROM swe_cron_executions e
                    INNER JOIN swe_cron_jobs j ON e.job_id = j.id
                    WHERE e.actual_time >= %s AND e.actual_time {time_compare} %s
                      AND j.status != 'deleted'
                      AND j.deleted_at IS NULL
                      AND j.source_id NOT IN ({cron_exclude_placeholders})
                      AND j.tenant_id != 'default'
                      {bbk_filter_sql}
                """
                query_params = (
                    s,
                    e,
                    *EXCLUDED_SOURCE_IDS,
                    *bbk_filter_params,
                )
            else:
                query = f"""
                    SELECT COUNT(*) as total
                    FROM swe_cron_executions e
                    INNER JOIN swe_cron_jobs j ON e.job_id = j.id
                    WHERE e.actual_time >= %s AND e.actual_time {time_compare} %s
                      AND j.status != 'deleted'
                      AND j.deleted_at IS NULL
                      AND j.tenant_id != 'default'
                      AND j.source_id = %s
                      {bbk_filter_sql}
                """
                query_params = (s, e, source_id, *bbk_filter_params)
            row = await self._db.fetch_one(query, query_params)
            return int((row or {}).get("total") or 0)

        curr = await get_stats(start_date, end_date, is_prev=False)
        prev = await get_stats(prev_start, prev_end, is_prev=True)
        curr_skill_calls = await get_skill_calls(
            start_date,
            end_date,
            is_prev=False,
        )
        prev_skill_calls = await get_skill_calls(
            prev_start,
            prev_end,
            is_prev=True,
        )
        curr_cron_tasks = await get_cron_tasks_count(
            start_date,
            end_date,
            is_prev=False,
        )
        prev_cron_tasks = await get_cron_tasks_count(
            prev_start,
            prev_end,
            is_prev=True,
        )

        # 深度指标与看板“使用深度”卡片口径保持一致：占比类指标和时长类
        # 指标都通过专用聚合函数获取，不与基础规模指标混算。
        curr_multi_round_ratio = await self._get_multi_round_ratio(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        )
        prev_multi_round_ratio = await self._get_multi_round_ratio(
            source_id,
            prev_start,
            prev_end,
            bbk_ids,
        )
        curr_avg_duration = await self._get_avg_duration_seconds(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        )
        prev_avg_duration = await self._get_avg_duration_seconds(
            source_id,
            prev_start,
            prev_end,
            bbk_ids,
        )

        def calc_growth(curr_val: float, prev_val: float) -> float | None:
            # 环比空值约定：
            # - 上期为 0 且本期有值：按 100% 展示，表示从无到有。
            # - 上期和本期都为 0：按 0.0 处理。
            # - 本期为 0 且上期有值：返回 None，由上层按“当前无数据”展示。
            if prev_val == 0:
                return 100.0 if curr_val > 0 else 0.0
            if curr_val == 0:
                # 当前周期无数据，上一周期有数据，返回 None 表示"当前无数据"
                return None
            return round(((curr_val - prev_val) / prev_val) * 100, 1)

        # 深度指标环比直接对齐页面卡片展示公式，保证卡片值与环比基线可追溯。
        # 1. 单次会话平均轮数环比 = 当前周期 calls/sessions 相对上一周期的变化。
        curr_avg_rounds = curr["calls"] / max(curr["sessions"], 1)
        prev_avg_rounds = prev["calls"] / max(prev["sessions"], 1)
        avg_rounds_growth = calc_growth(curr_avg_rounds, prev_avg_rounds)

        # 2. 多轮会话占比环比：以 >3 轮会话的占比作为口径。
        multi_round_ratio_growth = calc_growth(
            curr_multi_round_ratio,
            prev_multi_round_ratio,
        )

        # 3. 平均对话时长环比：以秒为单位比较。
        avg_duration_growth = calc_growth(curr_avg_duration, prev_avg_duration)

        # 4. 人均会话数环比 = 当前周期 sessions/users 相对上一周期的变化。
        curr_avg_sessions_per_user = curr["sessions"] / max(curr["users"], 1)
        prev_avg_sessions_per_user = prev["sessions"] / max(prev["users"], 1)
        avg_sessions_per_user_growth = calc_growth(
            curr_avg_sessions_per_user,
            prev_avg_sessions_per_user,
        )

        return {
            "callsGrowth": calc_growth(
                curr["calls"],
                prev["calls"],
            ),  # trace 记录数口径
            "tokensGrowth": calc_growth(
                curr["tokens"],
                prev["tokens"],
            ),  # total_tokens 汇总口径
            "sessionGrowth": calc_growth(
                curr["sessions"],
                prev["sessions"],
            ),  # session_id 去重口径
            "userGrowth": calc_growth(
                curr["users"],
                prev["users"],
            ),  # user_id 去重口径
            "skillGrowth": calc_growth(
                curr_skill_calls,
                prev_skill_calls,
            ),  # skill_invocation span 数口径
            "cronGrowth": calc_growth(
                curr_cron_tasks,
                prev_cron_tasks,
            ),  # cron 执行记录数口径
            "avgRoundsGrowth": avg_rounds_growth,  # 单次会话平均轮数口径
            "multiRoundRatioGrowth": multi_round_ratio_growth,  # >3 轮会话占比口径
            "avgDurationGrowth": avg_duration_growth,  # 平均对话时长（秒）口径
            "avgSessionsPerUserGrowth": avg_sessions_per_user_growth,  # 人均会话数口径
        }

    async def get_daily_trend(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """获取日趋势数据."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT
                    DATE(start_time) as date,
                    COUNT(*) as calls,
                    COALESCE(SUM(total_tokens), 0) as tokens,
                    COUNT(DISTINCT user_id) as users
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY DATE(start_time)
                ORDER BY date
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            rows = await self._db.fetch_all(query, params)
        else:
            query = f"""
                SELECT
                    DATE(start_time) as date,
                    COUNT(*) as calls,
                    COALESCE(SUM(total_tokens), 0) as tokens,
                    COUNT(DISTINCT user_id) as users
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY DATE(start_time)
                ORDER BY date
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            rows = await self._db.fetch_all(query, params)

        return [
            {
                "date": (
                    row["date"].strftime("%Y-%m-%d") if row["date"] else ""
                ),
                "calls": row["calls"] or 0,
                "tokens": row["tokens"] or 0,
                "users": row["users"] or 0,
            }
            for row in rows
        ]

    async def get_hourly_trend(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """获取单日按小时聚合的趋势数据。"""
        if start_date is None:
            start_date = datetime.now().replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        if end_date is None:
            end_date = start_date + timedelta(days=1)

        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT
                    HOUR(start_time) as hour_bucket,
                    COUNT(*) as calls,
                    COALESCE(SUM(total_tokens), 0) as tokens,
                    COUNT(DISTINCT user_id) as users
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY HOUR(start_time)
                ORDER BY hour_bucket
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            rows = await self._db.fetch_all(query, params)
        else:
            query = f"""
                SELECT
                    HOUR(start_time) as hour_bucket,
                    COUNT(*) as calls,
                    COALESCE(SUM(total_tokens), 0) as tokens,
                    COUNT(DISTINCT user_id) as users
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY HOUR(start_time)
                ORDER BY hour_bucket
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            rows = await self._db.fetch_all(query, params)

        hour_map = {
            int(row["hour_bucket"]): {
                "calls": row["calls"] or 0,
                "tokens": row["tokens"] or 0,
                "users": row["users"] or 0,
            }
            for row in rows
        }
        day_prefix = start_date.strftime("%Y-%m-%d")
        # 判断是否是今天：如果是今天，只返回到当前小时，避免显示未来无意义的时间点
        now = datetime.now()
        is_today = start_date.date() == now.date()
        max_hour = now.hour if is_today else 23
        return [
            {
                "date": f"{day_prefix} {hour:02d}:00",
                "calls": hour_map.get(hour, {}).get("calls", 0),
                "tokens": hour_map.get(hour, {}).get("tokens", 0),
                "users": hour_map.get(hour, {}).get("users", 0),
            }
            for hour in range(max_hour + 1)
        ]

    async def get_channel_distribution(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """获取渠道分布统计."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT
                    source_id,
                    COUNT(DISTINCT user_id) as user_count,
                    COUNT(*) as call_count,
                    SUM(total_tokens) as token_count
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id IS NOT NULL AND source_id != ''
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'
                GROUP BY source_id
                ORDER BY call_count DESC
            """
            rows = await self._db.fetch_all(
                query,
                (start_date, end_date, *EXCLUDED_SOURCE_IDS),
            )
        else:
            query = """
                SELECT
                    source_id,
                    COUNT(DISTINCT user_id) as user_count,
                    COUNT(*) as call_count,
                    SUM(total_tokens) as token_count
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND user_id != 'default'
                GROUP BY source_id
                ORDER BY call_count DESC
            """
            rows = await self._db.fetch_all(
                query,
                (source_id, start_date, end_date),
            )

        platform_user_dist = []
        platform_call_dist = []
        sources = []

        for row in rows:
            src_id = row["source_id"]
            sources.append(src_id)
            platform_user_dist.append(
                {"name": src_id, "value": row["user_count"] or 0},
            )
            platform_call_dist.append(
                {"name": src_id, "value": row["call_count"] or 0},
            )

        return {
            "platformUserDistribution": platform_user_dist,
            "platformCallDistribution": platform_call_dist,
            "totalPlatforms": len(sources),
        }

    async def get_sources(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[str]:
        """获取平台来源列表."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
        query = f"""
            SELECT DISTINCT source_id
            FROM swe_tracing_traces
            WHERE start_time >= %s AND start_time <= %s
              AND source_id IS NOT NULL AND source_id != ''
              AND source_id NOT IN ({exclude_placeholders})
            ORDER BY source_id
        """
        rows = await self._db.fetch_all(
            query,
            (start_date, end_date, *EXCLUDED_SOURCE_IDS),
        )
        return [row["source_id"] for row in rows]

    # ===== 用户分析 =====

    async def get_users(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_by: Optional[str] = None,
        filter_user_type: Optional[str] = "filtered",
        bbk_ids: Optional[str] = None,
    ) -> tuple[list[UserListItem], int]:
        """获取用户列表.

        Args:
            filter_user_type: 'filtered' 过滤80/IT开头用户，'all' 仅过滤default用户
        """
        order_by = "last_active DESC"
        if sort_by == "conversations":
            order_by = "total_conversations DESC"
        elif sort_by == "last_active":
            order_by = "last_active DESC"

        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            where_clauses = [f"source_id NOT IN ({exclude_placeholders})"]
            params: list[Any] = list(EXCLUDED_SOURCE_IDS)
        else:
            where_clauses = ["source_id = %s"]
            params = [source_id]

        # 用户过滤逻辑
        where_clauses.append("user_id != %s")
        params.append("default")
        if filter_user_type == "filtered":
            # 过滤掉以 80 开头或以 IT 开头的用户
            where_clauses.append(
                "(user_id NOT LIKE %s AND user_id NOT LIKE %s)",
            )
            params.append("80%")
            params.append("IT%")

        if user_id:
            where_clauses.append("user_id LIKE %s")
            params.append(f"%{user_id}%")
        if bbk_ids:
            bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
            where_clauses.append(
                f"bbk_id IN ({', '.join(['%s'] * len(bbk_params))})",
            )
            params.extend(bbk_params)
        if start_date:
            where_clauses.append("start_time >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("start_time <= %s")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses)

        count_query = f"SELECT COUNT(DISTINCT user_id) as total FROM swe_tracing_traces WHERE {where_sql}"
        count_row = await self._db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        offset = (page - 1) * page_size
        if source_id == "all":
            query = f"""
                SELECT t.user_id,
                       COUNT(DISTINCT t.session_id) as total_sessions,
                       COUNT(*) as total_conversations,
                       SUM(t.total_tokens) as total_tokens,
                       MAX(t.start_time) as last_active,
                       (SELECT COUNT(*) FROM swe_tracing_spans s
                        WHERE s.trace_id IN (SELECT trace_id FROM swe_tracing_traces WHERE user_id = t.user_id)
                        AND s.event_type = 'skill_invocation') as total_skills,
                       (SELECT user_name FROM swe_tracing_traces t2
                        WHERE t2.user_id = t.user_id AND t2.user_name IS NOT NULL
                        ORDER BY t2.start_time DESC LIMIT 1) as user_name,
                       (SELECT bbk_id FROM swe_tracing_traces t3
                        WHERE t3.user_id = t.user_id AND t3.bbk_id IS NOT NULL
                        ORDER BY t3.start_time DESC LIMIT 1) as bbk_id
                FROM swe_tracing_traces t
                WHERE {where_sql}
                GROUP BY t.user_id
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])
        else:
            query = f"""
                SELECT t.user_id,
                       COUNT(DISTINCT t.session_id) as total_sessions,
                       COUNT(*) as total_conversations,
                       SUM(t.total_tokens) as total_tokens,
                       MAX(t.start_time) as last_active,
                       (SELECT COUNT(*) FROM swe_tracing_spans s
                        WHERE s.source_id = %s
                        AND s.trace_id IN (SELECT trace_id FROM swe_tracing_traces WHERE user_id = t.user_id AND source_id = %s)
                        AND s.event_type = 'skill_invocation') as total_skills,
                       (SELECT user_name FROM swe_tracing_traces t2
                        WHERE t2.user_id = t.user_id AND t2.source_id = %s AND t2.user_name IS NOT NULL
                        ORDER BY t2.start_time DESC LIMIT 1) as user_name,
                       (SELECT bbk_id FROM swe_tracing_traces t3
                        WHERE t3.user_id = t.user_id AND t3.source_id = %s AND t3.bbk_id IS NOT NULL
                        ORDER BY t3.start_time DESC LIMIT 1) as bbk_id
                FROM swe_tracing_traces t
                WHERE {where_sql}
                GROUP BY t.user_id
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """
            params = (
                [source_id, source_id, source_id, source_id]
                + params
                + [page_size, offset]
            )

        rows = await self._db.fetch_all(query, tuple(params))
        users = [
            UserListItem(
                user_id=row["user_id"],
                user_name=row["user_name"],
                bbk_id=row["bbk_id"],
                total_sessions=row["total_sessions"] or 0,
                total_conversations=row["total_conversations"] or 0,
                total_tokens=row["total_tokens"] or 0,
                total_skills=row["total_skills"] or 0,
                last_active=row["last_active"],
            )
            for row in rows
        ]
        return users, total

    async def get_user_stats(
        self,
        source_id: str,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> UserStats:
        """获取用户统计详情."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()

        stats_row = await self._fetch_user_stats_row(
            source_id,
            user_id,
            start_date,
            end_date,
            bbk_ids,
        )
        model_usage, tools_used, skills_used, mcp_tools_used = (
            await self._fetch_user_usage_data(
                source_id,
                user_id,
                start_date,
                end_date,
                bbk_ids,
            )
        )

        return self._build_user_stats(
            user_id=user_id,
            stats_row=stats_row,
            model_usage=model_usage,
            tools_used=tools_used,
            skills_used=skills_used,
            mcp_tools_used=mcp_tools_used,
        )

    async def _fetch_user_stats_row(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> Optional[dict]:
        """获取用户统计行数据."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            query = f"""
                SELECT
                    COUNT(DISTINCT session_id) as total_sessions,
                    COUNT(*) as total_conversations,
                    SUM(total_input_tokens) as input_tokens,
                    SUM(total_output_tokens) as output_tokens,
                    SUM(total_tokens) as total_tokens,
                    AVG(duration_ms) as avg_duration
                FROM swe_tracing_traces
                WHERE user_id = %s AND start_time >= %s AND start_time <= %s{bbk_filter_sql}
            """
            return await self._db.fetch_one(
                query,
                (user_id, start_date, end_date, *bbk_filter_params),
            )

        query = f"""
            SELECT
                COUNT(DISTINCT session_id) as total_sessions,
                COUNT(*) as total_conversations,
                SUM(total_input_tokens) as input_tokens,
                SUM(total_output_tokens) as output_tokens,
                SUM(total_tokens) as total_tokens,
                AVG(duration_ms) as avg_duration
            FROM swe_tracing_traces
            WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s{bbk_filter_sql}
        """
        return await self._db.fetch_one(
            query,
            (source_id, user_id, start_date, end_date, *bbk_filter_params),
        )

    async def _fetch_user_usage_data(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> tuple:
        """并行获取用户使用数据."""
        return await asyncio.gather(
            self._get_user_model_usage(
                source_id,
                user_id,
                start_date,
                end_date,
                bbk_ids,
            ),
            self._get_user_tool_usage(
                source_id,
                user_id,
                start_date,
                end_date,
                bbk_ids,
            ),
            self._get_user_skill_usage(
                source_id,
                user_id,
                start_date,
                end_date,
                bbk_ids,
            ),
            self._get_user_mcp_tool_usage(
                source_id,
                user_id,
                start_date,
                end_date,
                bbk_ids,
            ),
        )

    def _build_user_stats(
        self,
        user_id: str,
        stats_row: Optional[dict],
        model_usage: list,
        tools_used: list,
        skills_used: list,
        mcp_tools_used: list,
    ) -> UserStats:
        """构建用户统计对象."""
        return UserStats(
            user_id=user_id,
            model_usage=model_usage,
            total_tokens=stats_row["total_tokens"] or 0 if stats_row else 0,
            input_tokens=stats_row["input_tokens"] or 0 if stats_row else 0,
            output_tokens=stats_row["output_tokens"] or 0 if stats_row else 0,
            total_sessions=(
                stats_row["total_sessions"] or 0 if stats_row else 0
            ),
            total_conversations=(
                stats_row["total_conversations"] or 0 if stats_row else 0
            ),
            avg_duration_ms=self._extract_avg_duration(stats_row),
            tools_used=tools_used,
            skills_used=skills_used,
            mcp_tools_used=mcp_tools_used,
        )

    # ===== 私有辅助方法 =====

    async def _get_total_users(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> int:
        """获取用户总数."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT COUNT(DISTINCT user_id) as total_users
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            row = await self._db.fetch_one(query, params)
        else:
            query = f"""
                SELECT COUNT(DISTINCT user_id) as total_users
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND user_id != 'default'{bbk_filter_sql}
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            row = await self._db.fetch_one(query, params)
        return row["total_users"] if row else 0

    async def _get_online_users(
        self,
        source_id: str,
        bbk_ids: Optional[str] = None,
    ) -> tuple[int, list[str]]:
        """获取在线用户."""
        online_threshold = datetime.now() - timedelta(minutes=5)
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            query = f"""
                SELECT DISTINCT user_id
                FROM swe_tracing_spans
                WHERE start_time >= %s AND user_id IS NOT NULL AND user_id != ''{bbk_filter_sql}
            """
            params = (online_threshold, *bbk_filter_params)
            rows = await self._db.fetch_all(query, params)
        else:
            query = f"""
                SELECT DISTINCT user_id
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND user_id IS NOT NULL AND user_id != ''{bbk_filter_sql}
            """
            params = (source_id, online_threshold, *bbk_filter_params)
            rows = await self._db.fetch_all(query, params)
        user_ids = [row["user_id"] for row in rows if row["user_id"]]
        return len(user_ids), user_ids

    async def _get_token_stats(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> Optional[dict]:
        """获取 Token 统计."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT
                    SUM(total_input_tokens) as input_tokens,
                    SUM(total_output_tokens) as output_tokens,
                    SUM(total_tokens) as total_tokens,
                    COUNT(*) as total_traces,
                    COUNT(DISTINCT session_id) as total_sessions,
                    AVG(duration_ms) as avg_duration
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            return await self._db.fetch_one(query, params)
        else:
            query = f"""
                SELECT
                    SUM(total_input_tokens) as input_tokens,
                    SUM(total_output_tokens) as output_tokens,
                    SUM(total_tokens) as total_tokens,
                    COUNT(*) as total_traces,
                    COUNT(DISTINCT session_id) as total_sessions,
                    AVG(duration_ms) as avg_duration
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND user_id != 'default'{bbk_filter_sql}
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            return await self._db.fetch_one(query, params)

    async def _get_model_distribution(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list[ModelUsage]:
        """获取模型分布."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT model_name, COUNT(*) as count,
                       SUM(total_input_tokens) as input_tokens,
                       SUM(total_output_tokens) as output_tokens,
                       SUM(total_tokens) as total_tokens
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s AND model_name IS NOT NULL
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY model_name
                ORDER BY count DESC
                LIMIT 10
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            rows = await self._db.fetch_all(query, params)
        else:
            query = f"""
                SELECT model_name, COUNT(*) as count,
                       SUM(total_input_tokens) as input_tokens,
                       SUM(total_output_tokens) as output_tokens,
                       SUM(total_tokens) as total_tokens
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s AND model_name IS NOT NULL
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY model_name
                ORDER BY count DESC
                LIMIT 10
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            rows = await self._db.fetch_all(query, params)
        return [
            ModelUsage(
                model_name=row["model_name"],
                count=row["count"] or 0,
                total_tokens=row["total_tokens"] or 0,
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
            )
            for row in rows
        ]

    async def _get_top_tools(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list[ToolUsage]:
        """获取热门工具."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT tool_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND tool_name IS NOT NULL
                  AND mcp_server IS NULL
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY tool_name
                ORDER BY count DESC
                LIMIT 10
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            rows = await self._db.fetch_all(query, params)
        else:
            query = f"""
                SELECT tool_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND tool_name IS NOT NULL
                  AND mcp_server IS NULL
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY tool_name
                ORDER BY count DESC
                LIMIT 10
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            rows = await self._db.fetch_all(query, params)
        return [
            ToolUsage(
                tool_name=row["tool_name"],
                count=row["count"] or 0,
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in rows
        ]

    async def _get_top_skills(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list[SkillUsage]:
        """获取热门技能."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT skill_name, MAX(skill_description) as skill_description,
                       COUNT(*) as count,
                       AVG(duration_ms) as avg_duration
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY skill_name
                ORDER BY count DESC
                LIMIT 10
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            rows = await self._db.fetch_all(query, params)
        else:
            query = f"""
                SELECT skill_name, MAX(skill_description) as skill_description,
                       COUNT(*) as count,
                       AVG(duration_ms) as avg_duration
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY skill_name
                ORDER BY count DESC
                LIMIT 10
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            rows = await self._db.fetch_all(query, params)
        return [
            SkillUsage(
                skill_name=row["skill_name"],
                skill_description=row["skill_description"] or "",
                count=row["count"] or 0,
                avg_duration_ms=int(row["avg_duration"] or 0),
            )
            for row in rows
        ]

    async def _get_total_skill_calls(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> int:
        """获取技能调用总次数（无 LIMIT）."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT COUNT(*) as total
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            row = await self._db.fetch_one(query, params)
        else:
            query = f"""
                SELECT COUNT(*) as total
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL
                  AND user_id != 'default'{bbk_filter_sql}
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            row = await self._db.fetch_one(query, params)
        return int((row or {}).get("total") or 0)

    async def _get_multi_round_ratio(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> float:
        """获取多轮会话占比(>3轮)的真实百分比.

        统计每个 session 的 trace 数量，计算超过3轮的 session 占比。
        """
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT
                    COUNT(*) as total_sessions,
                    SUM(CASE WHEN trace_count > 3 THEN 1 ELSE 0 END) as multi_round_sessions
                FROM (
                    SELECT session_id, COUNT(*) as trace_count
                    FROM swe_tracing_traces
                    WHERE start_time >= %s AND start_time <= %s
                      AND source_id NOT IN ({exclude_placeholders})
                      AND user_id != 'default'
                      AND session_id IS NOT NULL AND session_id != ''
                      {bbk_filter_sql}
                    GROUP BY session_id
                ) AS session_counts
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            row = await self._db.fetch_one(query, params)
        else:
            query = f"""
                SELECT
                    COUNT(*) as total_sessions,
                    SUM(CASE WHEN trace_count > 3 THEN 1 ELSE 0 END) as multi_round_sessions
                FROM (
                    SELECT session_id, COUNT(*) as trace_count
                    FROM swe_tracing_traces
                    WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                      AND user_id != 'default'
                      AND session_id IS NOT NULL AND session_id != ''
                      {bbk_filter_sql}
                    GROUP BY session_id
                ) AS session_counts
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            row = await self._db.fetch_one(query, params)

        total_sessions = int((row or {}).get("total_sessions") or 0)
        multi_round_sessions = int(
            (row or {}).get("multi_round_sessions") or 0,
        )
        if total_sessions == 0:
            return 0.0
        return round(multi_round_sessions / total_sessions * 100, 1)

    async def _get_avg_user_stay(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> int:
        """获取用户平均停留时长（秒）.

        统计每个用户在时间范围内从第一次请求到最后一次请求的时间差，
        然后计算平均值。
        """
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT AVG(stay_seconds) as avg_stay
                FROM (
                    SELECT user_id,
                           TIMESTAMPDIFF(SECOND, MIN(start_time), MAX(start_time)) as stay_seconds
                    FROM swe_tracing_traces
                    WHERE start_time >= %s AND start_time <= %s
                      AND source_id NOT IN ({exclude_placeholders})
                      AND user_id != 'default'
                      {bbk_filter_sql}
                    GROUP BY user_id
                    HAVING stay_seconds > 0
                ) AS user_stays
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            row = await self._db.fetch_one(query, params)
        else:
            query = f"""
                SELECT AVG(stay_seconds) as avg_stay
                FROM (
                    SELECT user_id,
                           TIMESTAMPDIFF(SECOND, MIN(start_time), MAX(start_time)) as stay_seconds
                    FROM swe_tracing_traces
                    WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                      AND user_id != 'default'
                      {bbk_filter_sql}
                    GROUP BY user_id
                    HAVING stay_seconds > 0
                ) AS user_stays
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            row = await self._db.fetch_one(query, params)

        avg_stay = float((row or {}).get("avg_stay") or 0)
        return int(avg_stay)

    async def _get_avg_duration_seconds(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> int:
        """获取平均对话时长（秒）.

        计算所有对话的平均耗时。
        """
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT AVG(duration_ms) as avg_duration_ms
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'
                  AND duration_ms IS NOT NULL
                  {bbk_filter_sql}
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            row = await self._db.fetch_one(query, params)
        else:
            query = f"""
                SELECT AVG(duration_ms) as avg_duration_ms
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND user_id != 'default'
                  AND duration_ms IS NOT NULL
                  {bbk_filter_sql}
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            row = await self._db.fetch_one(query, params)

        avg_duration_ms = float((row or {}).get("avg_duration_ms") or 0)
        # 转换为秒
        return int(avg_duration_ms / 1000)

    async def get_skills_paginated(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> tuple[list[SkillUsage], int]:
        """获取技能调用排行榜（分页）."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        # 构建基础查询条件
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            base_where = f"""
                start_time >= %s AND start_time <= %s
                AND event_type = 'skill_invocation'
                AND skill_name IS NOT NULL
                AND source_id NOT IN ({exclude_placeholders})
                AND user_id != 'default'{bbk_filter_sql}
            """
            count_params = [
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            ]
        else:
            base_where = f"""
                source_id = %s AND start_time >= %s AND start_time <= %s
                AND event_type = 'skill_invocation'
                AND skill_name IS NOT NULL
                AND user_id != 'default'{bbk_filter_sql}
            """
            count_params = [
                source_id,
                start_date,
                end_date,
                *bbk_filter_params,
            ]

        # 查询总数
        count_query = f"""
            SELECT COUNT(DISTINCT skill_name) as total
            FROM swe_tracing_spans
            WHERE {base_where}
        """
        count_row = await self._db.fetch_one(count_query, tuple(count_params))
        total = count_row["total"] if count_row else 0

        # 分页查询
        offset = (page - 1) * page_size
        data_query = f"""
            SELECT skill_name, MAX(skill_description) as skill_description,
                   COUNT(*) as count,
                   AVG(duration_ms) as avg_duration
            FROM swe_tracing_spans
            WHERE {base_where}
            GROUP BY skill_name
            ORDER BY count DESC
            LIMIT %s OFFSET %s
        """
        params = count_params + [page_size, offset]
        rows = await self._db.fetch_all(data_query, tuple(params))

        skills = [
            SkillUsage(
                skill_name=row["skill_name"],
                skill_description=row["skill_description"] or "",
                count=row["count"] or 0,
                avg_duration_ms=int(row["avg_duration"] or 0),
            )
            for row in rows
        ]
        return skills, total

    async def get_mcp_summary(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> MCPSummary:
        """获取 MCP 全局调用汇总统计."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        # 构建基础查询条件
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            base_where = f"""
                start_time >= %s AND start_time <= %s
                AND event_type = 'tool_call_end'
                AND mcp_server IS NOT NULL
                AND source_id NOT IN ({exclude_placeholders})
                AND user_id != 'default'{bbk_filter_sql}
            """
            params = [
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            ]
        else:
            base_where = f"""
                source_id = %s AND start_time >= %s AND start_time <= %s
                AND event_type = 'tool_call_end'
                AND mcp_server IS NOT NULL
                AND user_id != 'default'{bbk_filter_sql}
            """
            params = [
                source_id,
                start_date,
                end_date,
                *bbk_filter_params,
            ]

        # 全局汇总统计
        summary_query = f"""
            SELECT COUNT(*) as total_calls,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count,
                   COUNT(DISTINCT mcp_server) as server_count
            FROM swe_tracing_spans
            WHERE {base_where}
        """
        row = await self._db.fetch_one(summary_query, tuple(params))
        return MCPSummary(
            total_calls=row["total_calls"] or 0,
            error_count=row["error_count"] or 0,
            server_count=row["server_count"] or 0,
        )

    async def get_task_status_summary(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> TaskStatusSummary:
        """获取定时任务执行汇总统计."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        bbk_filter_sql, bbk_filter_params = build_cron_bbk_in_filter(bbk_ids)
        exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))

        if source_id == "all":
            query = f"""
                SELECT e.status, COUNT(*) AS count
                FROM swe_cron_executions e
                INNER JOIN swe_cron_jobs j ON e.job_id = j.id
                WHERE e.actual_time >= %s AND e.actual_time < %s
                  AND j.status != 'deleted'
                  AND j.deleted_at IS NULL
                  AND j.source_id NOT IN ({exclude_placeholders})
                  AND j.tenant_id != 'default'
                  {bbk_filter_sql}
                GROUP BY e.status
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
        else:
            query = f"""
                SELECT e.status, COUNT(*) AS count
                FROM swe_cron_executions e
                INNER JOIN swe_cron_jobs j ON e.job_id = j.id
                WHERE e.actual_time >= %s AND e.actual_time < %s
                  AND j.status != 'deleted'
                  AND j.deleted_at IS NULL
                  AND j.tenant_id != 'default'
                  AND j.source_id = %s
                  {bbk_filter_sql}
                GROUP BY e.status
            """
            params = (start_date, end_date, source_id, *bbk_filter_params)

        rows = await self._db.fetch_all(query, params)
        status_map = {row["status"]: row["count"] for row in rows}

        success = status_map.get("success", 0)
        failed = status_map.get("error", 0) + status_map.get("timeout", 0)
        cancelled = status_map.get("cancelled", 0) + status_map.get(
            "skipped",
            0,
        )
        total_tasks = success + failed + cancelled

        return TaskStatusSummary(
            total_tasks=total_tasks,
            success=success,
            failed=failed,
            cancelled=cancelled,
        )

    async def get_depth_summary(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> DepthSummary:
        """获取使用深度汇总统计."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))

        # 获取基础统计数据
        if source_id == "all":
            base_query = f"""
                SELECT
                    COUNT(*) as total_traces,
                    COUNT(DISTINCT session_id) as total_sessions,
                    COUNT(DISTINCT user_id) as total_users
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'
                  {bbk_filter_sql}
            """
            base_params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
        else:
            base_query = f"""
                SELECT
                    COUNT(*) as total_traces,
                    COUNT(DISTINCT session_id) as total_sessions,
                    COUNT(DISTINCT user_id) as total_users
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND user_id != 'default'
                  {bbk_filter_sql}
            """
            base_params = (source_id, start_date, end_date, *bbk_filter_params)

        base_row = await self._db.fetch_one(base_query, base_params)
        total_traces = int((base_row or {}).get("total_traces") or 0)
        total_sessions = max(
            int((base_row or {}).get("total_sessions") or 0),
            1,
        )
        total_users = max(int((base_row or {}).get("total_users") or 0), 1)

        # 单次会话平均轮数
        avg_rounds = round(total_traces / total_sessions, 1)

        # 人均会话数
        avg_sessions_per_user = round(total_sessions / total_users, 1)

        # 多轮会话占比 (>3轮)
        multi_round_ratio = await self._get_multi_round_ratio(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        )

        # 平均对话时长（秒）
        avg_duration_seconds = await self._get_avg_duration_seconds(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        )

        return DepthSummary(
            avg_rounds=avg_rounds,
            multi_round_ratio=multi_round_ratio,
            avg_duration_seconds=avg_duration_seconds,
            avg_sessions_per_user=avg_sessions_per_user,
        )

    async def get_mcp_servers_paginated(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> tuple[list[MCPServerUsage], int]:
        """获取 MCP 服务调用排行榜（分页）."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        # 构建基础查询条件
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            base_where = f"""
                start_time >= %s AND start_time <= %s
                AND event_type = 'tool_call_end'
                AND mcp_server IS NOT NULL
                AND source_id NOT IN ({exclude_placeholders})
                AND user_id != 'default'{bbk_filter_sql}
            """
            count_params = [
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            ]
        else:
            base_where = f"""
                source_id = %s AND start_time >= %s AND start_time <= %s
                AND event_type = 'tool_call_end'
                AND mcp_server IS NOT NULL
                AND user_id != 'default'{bbk_filter_sql}
            """
            count_params = [
                source_id,
                start_date,
                end_date,
                *bbk_filter_params,
            ]

        # 查询总数
        count_query = f"""
            SELECT COUNT(DISTINCT mcp_server) as total
            FROM swe_tracing_spans
            WHERE {base_where}
        """
        count_row = await self._db.fetch_one(count_query, tuple(count_params))
        total = count_row["total"] if count_row else 0

        # 分页查询
        offset = (page - 1) * page_size
        server_query = f"""
            SELECT mcp_server,
                   COUNT(DISTINCT tool_name) as tool_count,
                   COUNT(*) as total_calls,
                   AVG(duration_ms) as avg_duration,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM swe_tracing_spans
            WHERE {base_where}
            GROUP BY mcp_server
            ORDER BY total_calls DESC
            LIMIT %s OFFSET %s
        """
        params = count_params + [page_size, offset]
        server_rows = await self._db.fetch_all(server_query, tuple(params))

        mcp_servers = []
        for server_row in server_rows:
            server_name = server_row["mcp_server"]
            mcp_servers.append(
                MCPServerUsage(
                    server_name=server_name,
                    tool_count=server_row["tool_count"] or 0,
                    total_calls=server_row["total_calls"] or 0,
                    avg_duration_ms=int(server_row["avg_duration"] or 0),
                    error_count=server_row["error_count"] or 0,
                    tools=[],  # 分页查询不返回工具详情
                ),
            )
        return mcp_servers, total

    async def get_skill_traces(
        self,
        skill_name: str,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[TraceListItem], int]:
        """获取指定技能调用的对话列表（分页）."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        # 构建查询条件
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            base_where = f"""
                s.start_time >= %s AND s.start_time <= %s
                AND s.event_type = 'skill_invocation'
                AND s.skill_name = %s
                AND s.source_id NOT IN ({exclude_placeholders})
                AND s.user_id != 'default'
            """
            count_params = [
                start_date,
                end_date,
                skill_name,
                *EXCLUDED_SOURCE_IDS,
            ]
        else:
            base_where = """
                s.source_id = %s AND s.start_time >= %s AND s.start_time <= %s
                AND s.event_type = 'skill_invocation'
                AND s.skill_name = %s
                AND s.user_id != 'default'
            """
            count_params = [source_id, start_date, end_date, skill_name]

        # 查询总数
        count_query = f"""
            SELECT COUNT(DISTINCT s.trace_id) as total
            FROM swe_tracing_spans s
            WHERE {base_where}
        """
        count_row = await self._db.fetch_one(count_query, tuple(count_params))
        total = count_row["total"] if count_row else 0

        # 分页查询对话列表
        offset = (page - 1) * page_size
        if source_id == "all":
            data_query = f"""
                SELECT DISTINCT t.trace_id, t.source_id, t.user_id, t.session_id,
                       t.channel, t.start_time, t.duration_ms, t.total_tokens,
                       t.total_input_tokens, t.total_output_tokens, t.model_name,
                       t.status, JSON_LENGTH(t.skills_used) as skills_count,
                       (SELECT t2.user_name FROM swe_tracing_traces t2
                        WHERE t2.user_id = t.user_id AND t2.user_name IS NOT NULL
                        ORDER BY t2.start_time DESC LIMIT 1) as user_name,
                       (SELECT t3.bbk_id FROM swe_tracing_traces t3
                        WHERE t3.user_id = t.user_id AND t3.bbk_id IS NOT NULL
                        ORDER BY t3.start_time DESC LIMIT 1) as bbk_id
                FROM swe_tracing_spans s
                JOIN swe_tracing_traces t ON s.trace_id = t.trace_id
                WHERE {base_where}
                ORDER BY t.start_time ASC
                LIMIT %s OFFSET %s
            """
            params = list(count_params) + [page_size, offset]
        else:
            data_query = f"""
                SELECT DISTINCT t.trace_id, t.source_id, t.user_id, t.session_id,
                       t.channel, t.start_time, t.duration_ms, t.total_tokens,
                       t.total_input_tokens, t.total_output_tokens, t.model_name,
                       t.status, JSON_LENGTH(t.skills_used) as skills_count,
                       (SELECT t2.user_name FROM swe_tracing_traces t2
                        WHERE t2.user_id = t.user_id AND t2.source_id = %s
                          AND t2.user_name IS NOT NULL
                        ORDER BY t2.start_time DESC LIMIT 1) as user_name,
                       (SELECT t3.bbk_id FROM swe_tracing_traces t3
                        WHERE t3.user_id = t.user_id AND t3.source_id = %s
                          AND t3.bbk_id IS NOT NULL
                        ORDER BY t3.start_time DESC LIMIT 1) as bbk_id
                FROM swe_tracing_spans s
                JOIN swe_tracing_traces t ON s.trace_id = t.trace_id
                WHERE {base_where}
                ORDER BY t.start_time ASC
                LIMIT %s OFFSET %s
            """
            params = (
                [source_id, source_id]
                + list(count_params)
                + [page_size, offset]
            )

        rows = await self._db.fetch_all(data_query, tuple(params))

        traces = [
            TraceListItem(
                trace_id=row["trace_id"],
                source_id=row["source_id"],
                user_id=row["user_id"],
                user_name=row["user_name"],
                bbk_id=row["bbk_id"],
                session_id=row["session_id"],
                channel=row["channel"],
                start_time=row["start_time"],
                duration_ms=row["duration_ms"],
                total_tokens=row["total_tokens"] or 0,
                total_input_tokens=row["total_input_tokens"] or 0,
                total_output_tokens=row["total_output_tokens"] or 0,
                model_name=row["model_name"],
                status=row["status"],
                skills_count=row["skills_count"] or 0,
            )
            for row in rows
        ]
        return traces, total

    async def _get_mcp_stats(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> tuple[list[MCPToolUsage], list[MCPServerUsage]]:
        """获取 MCP 统计."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            mcp_tool_query = f"""
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                  AND tool_name IS NOT NULL
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
                LIMIT 10
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            mcp_tool_rows = await self._db.fetch_all(
                query=mcp_tool_query,
                params=params,
            )
        else:
            mcp_tool_query = f"""
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                  AND tool_name IS NOT NULL
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
                LIMIT 10
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            mcp_tool_rows = await self._db.fetch_all(
                query=mcp_tool_query,
                params=params,
            )

        top_mcp_tools = [
            MCPToolUsage(
                tool_name=row["tool_name"],
                mcp_server=row["mcp_server"],
                count=row["count"] or 0,
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in mcp_tool_rows
        ]

        # 获取 MCP 服务器统计（简化版本）
        mcp_servers = await self._get_mcp_servers(
            source_id,
            start_date,
            end_date,
            bbk_ids,
        )
        return top_mcp_tools, mcp_servers

    async def _get_mcp_servers(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list[MCPServerUsage]:
        """获取 MCP 服务器统计."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT mcp_server,
                       COUNT(DISTINCT tool_name) as tool_count,
                       COUNT(*) as total_calls,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY mcp_server
                ORDER BY total_calls DESC
            """
            params = (
                start_date,
                end_date,
                *EXCLUDED_SOURCE_IDS,
                *bbk_filter_params,
            )
            server_rows = await self._db.fetch_all(query, params)
        else:
            query = f"""
                SELECT mcp_server,
                       COUNT(DISTINCT tool_name) as tool_count,
                       COUNT(*) as total_calls,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                  AND user_id != 'default'{bbk_filter_sql}
                GROUP BY mcp_server
                ORDER BY total_calls DESC
            """
            params = (source_id, start_date, end_date, *bbk_filter_params)
            server_rows = await self._db.fetch_all(query, params)

        mcp_servers = []
        for server_row in server_rows:
            server_name = server_row["mcp_server"]
            tools = await self._get_server_tools(
                source_id,
                start_date,
                end_date,
                server_name,
                bbk_ids,
            )
            mcp_servers.append(
                MCPServerUsage(
                    server_name=server_name,
                    tool_count=server_row["tool_count"] or 0,
                    total_calls=server_row["total_calls"] or 0,
                    avg_duration_ms=int(server_row["avg_duration"] or 0),
                    error_count=server_row["error_count"] or 0,
                    tools=tools,
                ),
            )
        return mcp_servers

    async def _get_server_tools(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        server_name: str,
        bbk_ids: Optional[str] = None,
    ) -> list[MCPToolUsage]:
        """获取服务器工具统计."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            query = f"""
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server = %s
                  AND tool_name IS NOT NULL{bbk_filter_sql}
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
            """
            params = (start_date, end_date, server_name, *bbk_filter_params)
            rows = await self._db.fetch_all(query, params)
        else:
            query = f"""
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server = %s
                  AND tool_name IS NOT NULL{bbk_filter_sql}
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
            """
            params = (
                source_id,
                start_date,
                end_date,
                server_name,
                *bbk_filter_params,
            )
            rows = await self._db.fetch_all(query, params)
        return [
            MCPToolUsage(
                tool_name=r["tool_name"],
                mcp_server=r["mcp_server"],
                count=r["count"] or 0,
                avg_duration_ms=int(r["avg_duration"] or 0),
                error_count=r["error_count"] or 0,
            )
            for r in rows
        ]

    async def _get_user_model_usage(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list[ModelUsage]:
        """获取用户模型使用."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            model_query = f"""
                SELECT model_name, COUNT(*) as count,
                       SUM(total_input_tokens) as input_tokens,
                       SUM(total_output_tokens) as output_tokens,
                       SUM(total_tokens) as total_tokens
                FROM swe_tracing_traces
                WHERE user_id = %s AND start_time >= %s AND start_time <= %s
                      AND model_name IS NOT NULL{bbk_filter_sql}
                GROUP BY model_name
                ORDER BY count DESC
            """
            model_rows = await self._db.fetch_all(
                model_query,
                (user_id, start_date, end_date, *bbk_filter_params),
            )
        else:
            model_query = f"""
                SELECT model_name, COUNT(*) as count,
                       SUM(total_input_tokens) as input_tokens,
                       SUM(total_output_tokens) as output_tokens,
                       SUM(total_tokens) as total_tokens
                FROM swe_tracing_traces
                WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s
                      AND model_name IS NOT NULL{bbk_filter_sql}
                GROUP BY model_name
                ORDER BY count DESC
            """
            model_rows = await self._db.fetch_all(
                model_query,
                (source_id, user_id, start_date, end_date, *bbk_filter_params),
            )
        return [
            ModelUsage(
                model_name=row["model_name"],
                count=row["count"],
                total_tokens=row["total_tokens"] or 0,
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
            )
            for row in model_rows
        ]

    async def _get_user_tool_usage(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list[ToolUsage]:
        """获取用户工具使用."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            tool_query = f"""
                SELECT tool_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE user_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND tool_name IS NOT NULL{bbk_filter_sql}
                GROUP BY tool_name
                ORDER BY count DESC
            """
            tool_rows = await self._db.fetch_all(
                tool_query,
                (user_id, start_date, end_date, *bbk_filter_params),
            )
        else:
            tool_query = f"""
                SELECT tool_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND tool_name IS NOT NULL{bbk_filter_sql}
                GROUP BY tool_name
                ORDER BY count DESC
            """
            tool_rows = await self._db.fetch_all(
                tool_query,
                (source_id, user_id, start_date, end_date, *bbk_filter_params),
            )
        return [
            ToolUsage(
                tool_name=row["tool_name"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in tool_rows
        ]

    async def _get_user_skill_usage(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list[SkillUsage]:
        """获取用户技能使用."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            skill_query = f"""
                SELECT skill_name, MAX(skill_description) as skill_description,
                       COUNT(*) as count,
                       AVG(duration_ms) as avg_duration
                FROM swe_tracing_spans
                WHERE user_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL{bbk_filter_sql}
                GROUP BY skill_name
                ORDER BY count DESC
            """
            skill_rows = await self._db.fetch_all(
                skill_query,
                (user_id, start_date, end_date, *bbk_filter_params),
            )
        else:
            skill_query = f"""
                SELECT skill_name, MAX(skill_description) as skill_description,
                       COUNT(*) as count,
                       AVG(duration_ms) as avg_duration
                FROM swe_tracing_spans
                WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL{bbk_filter_sql}
                GROUP BY skill_name
                ORDER BY count DESC
            """
            skill_rows = await self._db.fetch_all(
                skill_query,
                (source_id, user_id, start_date, end_date, *bbk_filter_params),
            )

        return [
            SkillUsage(
                skill_name=row["skill_name"],
                skill_description=row["skill_description"] or "",
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
            )
            for row in skill_rows
        ]

    async def _get_user_mcp_tool_usage(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list[MCPToolUsage]:
        """获取用户 MCP 工具使用."""
        bbk_filter_sql, bbk_filter_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            query = f"""
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE user_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                  AND tool_name IS NOT NULL{bbk_filter_sql}
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
            """
            rows = await self._db.fetch_all(
                query,
                (user_id, start_date, end_date, *bbk_filter_params),
            )
        else:
            query = f"""
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                  AND tool_name IS NOT NULL{bbk_filter_sql}
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
            """
            rows = await self._db.fetch_all(
                query,
                (source_id, user_id, start_date, end_date, *bbk_filter_params),
            )
        return [
            MCPToolUsage(
                tool_name=row["tool_name"],
                mcp_server=row["mcp_server"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in rows
        ]

    # ===== 会话分析 =====

    async def get_sessions(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> tuple[list[SessionListItem], int]:
        """获取会话列表."""
        if source_id == "all":
            exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            where_clauses: list[str] = [
                f"source_id NOT IN ({exclude_placeholders})",
            ]
            params: list[Any] = list(EXCLUDED_SOURCE_IDS)
        else:
            where_clauses = ["source_id = %s"]
            params = [source_id]

        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        if session_id:
            where_clauses.append("session_id LIKE %s")
            params.append(f"%{session_id}%")
        if bbk_ids:
            bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
            where_clauses.append(
                f"bbk_id IN ({', '.join(['%s'] * len(bbk_params))})",
            )
            params.extend(bbk_params)
        if start_date:
            where_clauses.append("start_time >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("start_time <= %s")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # 构建技能统计子查询的日期筛选条件
        skill_date_conditions = "s.event_type = 'skill_invocation'"
        skill_params: list[Any] = []
        if start_date:
            skill_date_conditions += " AND s.start_time >= %s"
            skill_params.append(start_date)
        if end_date:
            skill_date_conditions += " AND s.start_time <= %s"
            skill_params.append(end_date)

        count_query = f"SELECT COUNT(DISTINCT session_id) as total FROM swe_tracing_traces WHERE {where_sql}"
        count_row = await self._db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        offset = (page - 1) * page_size
        exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
        if source_id == "all":
            # SQL 占位符顺序（按在 SQL 字符串中出现顺序）：
            # 1. SELECT 子查询1: s.source_id NOT IN (...)
            # 2. SELECT 子查询1: {skill_date_conditions} 的日期参数
            # 3. SELECT 子查询2: t2.source_id NOT IN (...)
            # 4. SELECT 子查询3: t3.source_id NOT IN (...)
            # 5. SELECT 子查询4: t4.source_id NOT IN (...) (session_name)
            # 6. SELECT 子查询5: t5.source_id NOT IN (...) (user_message fallback)
            # 7. WHERE {where_sql} 的参数
            # 8. LIMIT %s OFFSET %s
            query = f"""
                SELECT t.session_id,
                       t.user_id,
                       t.channel,
                       COUNT(*) as total_traces,
                       SUM(t.total_tokens) as total_tokens,
                       MIN(t.start_time) as first_active,
                       MAX(t.start_time) as last_active,
                       (SELECT COUNT(*) FROM swe_tracing_spans s
                        WHERE s.session_id = t.session_id
                        AND s.source_id NOT IN ({exclude_placeholders})
                        AND {skill_date_conditions}) as total_skills,
                       (SELECT t2.user_name FROM swe_tracing_traces t2
                        WHERE t2.user_id = t.user_id AND t2.user_name IS NOT NULL
                        AND t2.source_id NOT IN ({exclude_placeholders})
                        ORDER BY t2.start_time DESC LIMIT 1) as user_name,
                       (SELECT t3.bbk_id FROM swe_tracing_traces t3
                        WHERE t3.user_id = t.user_id AND t3.bbk_id IS NOT NULL
                        AND t3.source_id NOT IN ({exclude_placeholders})
                        ORDER BY t3.start_time DESC LIMIT 1) as bbk_id,
                       COALESCE(
                           (SELECT t4.session_name FROM swe_tracing_traces t4
                            WHERE t4.session_id = t.session_id AND t4.session_name IS NOT NULL
                            AND t4.source_id NOT IN ({exclude_placeholders})
                            ORDER BY t4.start_time ASC LIMIT 1),
                           SUBSTRING(
                               (SELECT t5.user_message FROM swe_tracing_traces t5
                                WHERE t5.session_id = t.session_id AND t5.user_message IS NOT NULL
                                AND t5.source_id NOT IN ({exclude_placeholders})
                                ORDER BY t5.start_time ASC LIMIT 1),
                               1, 10
                           )
                       ) as session_name
                FROM swe_tracing_traces t
                WHERE {where_sql}
                GROUP BY t.session_id, t.user_id, t.channel
                ORDER BY last_active DESC
                LIMIT %s OFFSET %s
            """
            # 参数按 SQL 占位符出现顺序构建：
            # 子查询1参数 + 子查询2参数 + 子查询3参数 + 子查询4参数 + 子查询5参数 + WHERE参数 + LIMIT/OFFSET
            params = (
                list(EXCLUDED_SOURCE_IDS)  # 子查询1: s.source_id NOT IN
                + skill_params  # 子查询1: 日期条件
                + list(EXCLUDED_SOURCE_IDS)  # 子查询2: t2.source_id NOT IN
                + list(EXCLUDED_SOURCE_IDS)  # 子查询3: t3.source_id NOT IN
                + list(
                    EXCLUDED_SOURCE_IDS,
                )  # 子查询4: t4.source_id NOT IN (session_name)
                + list(
                    EXCLUDED_SOURCE_IDS,
                )  # 子查询5: t5.source_id NOT IN (user_message fallback)
                + params  # WHERE 子句参数
                + [page_size, offset]
            )
        else:
            query = f"""
                SELECT t.session_id,
                       t.user_id,
                       t.channel,
                       COUNT(*) as total_traces,
                       SUM(t.total_tokens) as total_tokens,
                       MIN(t.start_time) as first_active,
                       MAX(t.start_time) as last_active,
                       (SELECT COUNT(*) FROM swe_tracing_spans s
                        WHERE s.source_id = %s
                        AND s.session_id = t.session_id
                        AND {skill_date_conditions}) as total_skills,
                       (SELECT t2.user_name FROM swe_tracing_traces t2
                        WHERE t2.user_id = t.user_id AND t2.source_id = %s AND t2.user_name IS NOT NULL
                        ORDER BY t2.start_time DESC LIMIT 1) as user_name,
                       (SELECT t3.bbk_id FROM swe_tracing_traces t3
                        WHERE t3.user_id = t.user_id AND t3.source_id = %s AND t3.bbk_id IS NOT NULL
                        ORDER BY t3.start_time DESC LIMIT 1) as bbk_id,
                       COALESCE(
                           (SELECT t4.session_name FROM swe_tracing_traces t4
                            WHERE t4.session_id = t.session_id AND t4.session_name IS NOT NULL
                            AND t4.source_id = %s
                            ORDER BY t4.start_time ASC LIMIT 1),
                           SUBSTRING(
                               (SELECT t5.user_message FROM swe_tracing_traces t5
                                WHERE t5.session_id = t.session_id AND t5.user_message IS NOT NULL
                                AND t5.source_id = %s
                                ORDER BY t5.start_time ASC LIMIT 1),
                               1, 10
                           )
                       ) as session_name
                FROM swe_tracing_traces t
                WHERE {where_sql}
                GROUP BY t.session_id, t.user_id, t.channel
                ORDER BY last_active DESC
                LIMIT %s OFFSET %s
            """
            # 参数顺序: 子查询1 + 子查询2 + 子查询3 + 子查询4 + 子查询5 + WHERE参数 + LIMIT/OFFSET
            params = (
                [source_id]
                + skill_params
                + [source_id, source_id, source_id, source_id]
                + params
                + [page_size, offset]
            )

        rows = await self._db.fetch_all(query, tuple(params))
        sessions = [
            SessionListItem(
                session_id=row["session_id"],
                session_name=row.get("session_name"),
                user_id=row["user_id"],
                user_name=row["user_name"],
                bbk_id=row["bbk_id"],
                channel=row["channel"],
                total_traces=row["total_traces"] or 0,
                total_tokens=row["total_tokens"] or 0,
                total_skills=row["total_skills"] or 0,
                first_active=row["first_active"],
                last_active=row["last_active"],
            )
            for row in rows
        ]
        return sessions, total

    async def get_session_stats(
        self,
        source_id: str,
        session_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> SessionStats:
        """获取会话统计详情."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()

        stats_row = await self._fetch_session_stats_row(
            source_id,
            session_id,
            start_date,
            end_date,
            bbk_ids,
        )

        if not stats_row or not stats_row.get("user_id"):
            return SessionStats(session_id=session_id, user_id="", channel="")

        user_id = stats_row["user_id"]
        channel = stats_row["channel"] or ""

        model_usage, tools_used, skills_used, mcp_tools_used = (
            await asyncio.gather(
                self._fetch_session_model_usage(
                    source_id,
                    session_id,
                    start_date,
                    end_date,
                    bbk_ids,
                ),
                self._fetch_session_tools_used(
                    source_id,
                    session_id,
                    start_date,
                    end_date,
                    bbk_ids,
                ),
                self._fetch_session_skills_used(
                    source_id,
                    session_id,
                    start_date,
                    end_date,
                    bbk_ids,
                ),
                self._fetch_session_mcp_tools(
                    source_id,
                    session_id,
                    start_date,
                    end_date,
                    bbk_ids,
                ),
            )
        )

        return self._build_session_stats(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            stats_row=stats_row,
            model_usage_rows=model_usage,
            tools_used_rows=tools_used,
            skills_used_rows=skills_used,
            mcp_tools_rows=mcp_tools_used,
        )

    async def _fetch_session_stats_row(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> Optional[dict]:
        """获取会话统计行数据."""
        bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            query = f"""
                SELECT
                    user_id,
                    channel,
                    COUNT(*) as total_traces,
                    SUM(total_input_tokens) as input_tokens,
                    SUM(total_output_tokens) as output_tokens,
                    SUM(total_tokens) as total_tokens,
                    AVG(duration_ms) as avg_duration,
                    MIN(start_time) as first_active,
                    MAX(start_time) as last_active
                FROM swe_tracing_traces
                WHERE source_id NOT IN ({exclude_placeholders})
                      AND session_id = %s AND start_time >= %s AND start_time <= %s
                      {bbk_filter_sql}
                GROUP BY user_id, channel
            """
            return await self._db.fetch_one(
                query,
                (
                    *EXCLUDED_SOURCE_IDS,
                    session_id,
                    start_date,
                    end_date,
                    *bbk_params,
                ),
            )
        return await self._db.fetch_one(
            f"""
            SELECT
                user_id,
                channel,
                COUNT(*) as total_traces,
                SUM(total_input_tokens) as input_tokens,
                SUM(total_output_tokens) as output_tokens,
                SUM(total_tokens) as total_tokens,
                AVG(duration_ms) as avg_duration,
                MIN(start_time) as first_active,
                MAX(start_time) as last_active
            FROM swe_tracing_traces
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
                  {bbk_filter_sql}
            GROUP BY user_id, channel
            """,
            (source_id, session_id, start_date, end_date, *bbk_params),
        )

    async def _fetch_session_model_usage(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list:
        """获取会话模型使用数据."""
        bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            query = f"""
                SELECT model_name, COUNT(*) as count,
                       SUM(total_input_tokens) as input_tokens,
                       SUM(total_output_tokens) as output_tokens,
                       SUM(total_tokens) as total_tokens
                FROM swe_tracing_traces
                WHERE source_id NOT IN ({exclude_placeholders})
                      AND session_id = %s AND start_time >= %s AND start_time <= %s
                      AND model_name IS NOT NULL
                      {bbk_filter_sql}
                GROUP BY model_name
                ORDER BY count DESC
            """
            return await self._db.fetch_all(
                query,
                (
                    *EXCLUDED_SOURCE_IDS,
                    session_id,
                    start_date,
                    end_date,
                    *bbk_params,
                ),
            )
        return await self._db.fetch_all(
            f"""
            SELECT model_name, COUNT(*) as count,
                   SUM(total_input_tokens) as input_tokens,
                   SUM(total_output_tokens) as output_tokens,
                   SUM(total_tokens) as total_tokens
            FROM swe_tracing_traces
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
                  AND model_name IS NOT NULL
                  {bbk_filter_sql}
            GROUP BY model_name
            ORDER BY count DESC
            """,
            (source_id, session_id, start_date, end_date, *bbk_params),
        )

    async def _fetch_session_tools_used(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list:
        """获取会话工具使用数据."""
        bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            query = f"""
                SELECT tool_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id NOT IN ({exclude_placeholders})
                      AND session_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND tool_name IS NOT NULL
                  AND mcp_server IS NULL
                  {bbk_filter_sql}
                GROUP BY tool_name
                ORDER BY count DESC
            """
            return await self._db.fetch_all(
                query,
                (
                    *EXCLUDED_SOURCE_IDS,
                    session_id,
                    start_date,
                    end_date,
                    *bbk_params,
                ),
            )
        return await self._db.fetch_all(
            f"""
            SELECT tool_name, COUNT(*) as count,
                   AVG(duration_ms) as avg_duration,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM swe_tracing_spans
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
              AND event_type = 'tool_call_end'
              AND tool_name IS NOT NULL
              AND mcp_server IS NULL
              {bbk_filter_sql}
            GROUP BY tool_name
            ORDER BY count DESC
            """,
            (source_id, session_id, start_date, end_date, *bbk_params),
        )

    async def _fetch_session_skills_used(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list:
        """获取会话技能使用数据."""
        bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            query = f"""
                SELECT skill_name, MAX(skill_description) as skill_description,
                       COUNT(*) as count,
                       AVG(duration_ms) as avg_duration
                FROM swe_tracing_spans
                WHERE source_id NOT IN ({exclude_placeholders})
                      AND session_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL
                  {bbk_filter_sql}
                GROUP BY skill_name
                ORDER BY count DESC
            """
            return await self._db.fetch_all(
                query,
                (
                    *EXCLUDED_SOURCE_IDS,
                    session_id,
                    start_date,
                    end_date,
                    *bbk_params,
                ),
            )
        return await self._db.fetch_all(
            f"""
            SELECT skill_name, MAX(skill_description) as skill_description,
                   COUNT(*) as count,
                   AVG(duration_ms) as avg_duration
            FROM swe_tracing_spans
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
              AND event_type = 'skill_invocation'
              AND skill_name IS NOT NULL
              {bbk_filter_sql}
            GROUP BY skill_name
            ORDER BY count DESC
            """,
            (source_id, session_id, start_date, end_date, *bbk_params),
        )

    async def _fetch_session_mcp_tools(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
        bbk_ids: Optional[str] = None,
    ) -> list:
        """获取会话 MCP 工具使用数据."""
        bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
        if source_id == "all":
            exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            query = f"""
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id NOT IN ({exclude_placeholders})
                      AND session_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                  {bbk_filter_sql}
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
            """
            return await self._db.fetch_all(
                query,
                (
                    *EXCLUDED_SOURCE_IDS,
                    session_id,
                    start_date,
                    end_date,
                    *bbk_params,
                ),
            )
        return await self._db.fetch_all(
            f"""
            SELECT tool_name, mcp_server, COUNT(*) as count,
                   AVG(duration_ms) as avg_duration,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM swe_tracing_spans
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
              AND event_type = 'tool_call_end'
              AND mcp_server IS NOT NULL
              {bbk_filter_sql}
            GROUP BY tool_name, mcp_server
            ORDER BY count DESC
            """,
            (source_id, session_id, start_date, end_date, *bbk_params),
        )

    def _build_session_stats(
        self,
        session_id: str,
        user_id: str,
        channel: str,
        stats_row: dict,
        model_usage_rows: list,
        tools_used_rows: list,
        skills_used_rows: list,
        mcp_tools_rows: list,
    ) -> SessionStats:
        """构建会话统计对象."""
        return SessionStats(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            model_usage=self._build_model_usage_list(model_usage_rows),
            total_tokens=stats_row["total_tokens"] or 0,
            input_tokens=stats_row["input_tokens"] or 0,
            output_tokens=stats_row["output_tokens"] or 0,
            total_traces=stats_row["total_traces"] or 0,
            avg_duration_ms=self._extract_avg_duration(stats_row),
            tools_used=self._build_tool_usage_list(tools_used_rows),
            skills_used=self._build_skill_usage_list(skills_used_rows),
            mcp_tools_used=self._build_mcp_tool_usage_list(mcp_tools_rows),
            first_active=stats_row["first_active"],
            last_active=stats_row["last_active"],
        )

    def _build_model_usage_list(self, rows: list) -> list[ModelUsage]:
        """构建模型使用列表."""
        return [
            ModelUsage(
                model_name=row["model_name"],
                count=row["count"],
                total_tokens=row["total_tokens"] or 0,
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
            )
            for row in rows
        ]

    def _build_tool_usage_list(self, rows: list) -> list[ToolUsage]:
        """构建工具使用列表."""
        return [
            ToolUsage(
                tool_name=row["tool_name"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in rows
        ]

    def _build_skill_usage_list(self, rows: list) -> list[SkillUsage]:
        """构建技能使用列表."""
        return [
            SkillUsage(
                skill_name=row["skill_name"],
                skill_description=row.get("skill_description", "") or "",
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
            )
            for row in rows
        ]

    def _build_mcp_tool_usage_list(self, rows: list) -> list[MCPToolUsage]:
        """构建 MCP 工具使用列表."""
        return [
            MCPToolUsage(
                tool_name=row["tool_name"],
                mcp_server=row["mcp_server"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in rows
        ]

    # ===== 对话分析 =====

    async def get_traces(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bbk_ids: Optional[str] = None,
    ) -> tuple[list[TraceListItem], int]:
        """获取对话列表."""
        if source_id == "all":
            exclude_placeholders = ", ".join(
                ["%s"] * len(EXCLUDED_SOURCE_IDS),
            )
            where_clauses: list[str] = [
                f"t.source_id NOT IN ({exclude_placeholders})",
            ]
            params: list[Any] = list(EXCLUDED_SOURCE_IDS)
        else:
            where_clauses = ["t.source_id = %s"]
            params = [source_id]

        if user_id:
            where_clauses.append("t.user_id = %s")
            params.append(user_id)
        if session_id:
            where_clauses.append("t.session_id = %s")
            params.append(session_id)
        if status:
            where_clauses.append("t.status = %s")
            params.append(status)
        if bbk_ids:
            bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
            where_clauses.append(
                f"bbk_id IN ({', '.join(['%s'] * len(bbk_params))})",
            )
            params.extend(bbk_params)
        if start_date:
            where_clauses.append("t.start_time >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("t.start_time <= %s")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_query = f"SELECT COUNT(*) as total FROM swe_tracing_traces t WHERE {where_sql}"
        count_row = await self._db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        offset = (page - 1) * page_size
        exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
        if source_id == "all":
            query = f"""
                SELECT t.trace_id, t.source_id, t.user_id, t.session_id, t.channel, t.start_time,
                       t.duration_ms, t.total_tokens, t.total_input_tokens, t.total_output_tokens,
                       t.model_name, t.status,
                       JSON_LENGTH(t.skills_used) as skills_count,
                       {FEEDBACK_SELECT_SQL},
                       COALESCE(t.user_name, (
                           SELECT t2.user_name FROM swe_tracing_traces t2
                           WHERE t2.user_id = t.user_id AND t2.user_name IS NOT NULL
                           AND t2.source_id NOT IN ({exclude_placeholders})
                           ORDER BY t2.start_time DESC LIMIT 1
                       )) as user_name,
                       COALESCE(t.bbk_id, (
                           SELECT t3.bbk_id FROM swe_tracing_traces t3
                           WHERE t3.user_id = t.user_id AND t3.bbk_id IS NOT NULL
                           AND t3.source_id NOT IN ({exclude_placeholders})
                           ORDER BY t3.start_time DESC LIMIT 1
                       )) as bbk_id
                FROM swe_tracing_traces t
                {LATEST_FEEDBACK_JOIN_SQL}
                WHERE {where_sql}
                ORDER BY t.start_time DESC
                LIMIT %s OFFSET %s
            """
            # 参数顺序：子查询参数（按 SQL 出现顺序）+ WHERE 参数 + LIMIT/OFFSET
            params = (
                list(EXCLUDED_SOURCE_IDS)  # 子查询1: t2.source_id NOT IN
                + list(EXCLUDED_SOURCE_IDS)  # 子查询2: t3.source_id NOT IN
                + params  # WHERE 子句参数
                + [page_size, offset]
            )
        else:
            query = f"""
                SELECT t.trace_id, t.source_id, t.user_id, t.session_id, t.channel, t.start_time,
                       t.duration_ms, t.total_tokens, t.total_input_tokens, t.total_output_tokens,
                       t.model_name, t.status,
                       JSON_LENGTH(t.skills_used) as skills_count,
                       {FEEDBACK_SELECT_SQL},
                       COALESCE(t.user_name, (
                           SELECT t2.user_name FROM swe_tracing_traces t2
                           WHERE t2.source_id = %s AND t2.user_id = t.user_id AND t2.user_name IS NOT NULL
                           ORDER BY t2.start_time DESC LIMIT 1
                       )) as user_name,
                       COALESCE(t.bbk_id, (
                           SELECT t3.bbk_id FROM swe_tracing_traces t3
                           WHERE t3.source_id = %s AND t3.user_id = t.user_id AND t3.bbk_id IS NOT NULL
                           ORDER BY t3.start_time DESC LIMIT 1
                       )) as bbk_id
                FROM swe_tracing_traces t
                {LATEST_FEEDBACK_JOIN_SQL}
                WHERE {where_sql}
                ORDER BY t.start_time DESC
                LIMIT %s OFFSET %s
            """
            params = [source_id, source_id] + params + [page_size, offset]
        rows = await self._db.fetch_all(query, tuple(params))
        traces = [
            TraceListItem(
                trace_id=row["trace_id"],
                source_id=row["source_id"],
                user_id=row["user_id"],
                user_name=row["user_name"],
                bbk_id=row["bbk_id"],
                session_id=row["session_id"],
                channel=row["channel"],
                start_time=row["start_time"],
                duration_ms=row["duration_ms"],
                total_tokens=row["total_tokens"] or 0,
                total_input_tokens=row["total_input_tokens"] or 0,
                total_output_tokens=row["total_output_tokens"] or 0,
                model_name=row["model_name"],
                status=row["status"],
                skills_count=row["skills_count"] or 0,
                feedback=_row_to_feedback(row),
            )
            for row in rows
        ]
        return traces, total

    async def get_trace(
        self,
        trace_id: str,
        source_id: Optional[str] = None,
    ) -> Optional[Trace]:
        """获取单个对话."""
        if source_id:
            query = "SELECT * FROM swe_tracing_traces WHERE trace_id = %s AND source_id = %s"
            row = await self._db.fetch_one(query, (trace_id, source_id))
        else:
            query = "SELECT * FROM swe_tracing_traces WHERE trace_id = %s"
            row = await self._db.fetch_one(query, (trace_id,))
        if row is None:
            return None
        return self._row_to_trace(row)

    async def get_spans(self, trace_id: str) -> list[Span]:
        """获取对话的所有 Span."""
        query = "SELECT * FROM swe_tracing_spans WHERE trace_id = %s ORDER BY start_time"
        rows = await self._db.fetch_all(query, (trace_id,))
        return [self._row_to_span(row) for row in rows]

    async def get_trace_feedback(
        self,
        trace_id: str,
        source_id: Optional[str],
    ) -> Optional[TraceFeedback]:
        """获取对话关联的最新反馈。"""
        query = """
            SELECT
                id as feedback_id,
                source_id as feedback_source_id,
                feedback_user_name,
                feedback_user_sap,
                feedback_branch,
                feedback_sub_branch,
                feedback_position,
                cron_task_name as feedback_cron_task_name,
                cron_task_id as feedback_cron_task_id,
                response_id as feedback_response_id,
                trace_id as feedback_trace_id,
                chat_id as feedback_chat_id,
                session_id as feedback_session_id,
                feedback_options,
                feedback_content,
                created_at as feedback_created_at,
                updated_at as feedback_updated_at
            FROM swe_response_feedback
            WHERE trace_id COLLATE utf8mb4_unicode_ci = CAST(%s AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci
              AND source_id COLLATE utf8mb4_unicode_ci <=> CAST(%s AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci
            ORDER BY id DESC
            LIMIT 1
        """
        row = await self._db.fetch_one(query, (trace_id, source_id))
        if not row:
            return None
        return _row_to_feedback(row)

    async def get_trace_detail(
        self,
        trace_id: str,
        source_id: Optional[str] = None,
    ) -> Optional[TraceDetail]:
        """获取对话详情."""
        trace = await self.get_trace(trace_id, source_id)
        if trace is None:
            return None

        spans = await self.get_spans(trace_id)

        # 从 ES 获取 model_output
        from ...database.elasticsearch import get_es_client

        es_client = get_es_client()
        if es_client and es_client.is_connected:
            trace.model_output = await es_client.get_message(trace_id)

        feedback = await self.get_trace_feedback(trace_id, trace.source_id)

        llm_duration = sum(
            s.duration_ms or 0
            for s in spans
            if s.event_type in (EventType.LLM_INPUT, EventType.LLM_OUTPUT)
        )
        tool_duration = sum(
            s.duration_ms or 0
            for s in spans
            if s.event_type
            in (EventType.TOOL_CALL_START, EventType.TOOL_CALL_END)
        )

        tools_called = []
        tool_spans = [
            s for s in spans if s.event_type == EventType.TOOL_CALL_END
        ]
        for span in tool_spans:
            tools_called.append(
                {
                    "tool_name": span.tool_name or span.name,
                    "tool_input": span.tool_input,
                    "tool_output": span.tool_output,
                    "duration_ms": span.duration_ms,
                    "error": span.error,
                },
            )

        return TraceDetail(
            trace=trace,
            spans=spans,
            llm_duration_ms=llm_duration,
            tool_duration_ms=tool_duration,
            tools_called=tools_called,
            feedback=feedback,
        )

    async def get_trace_detail_with_timeline(
        self,
        trace_id: str,
        source_id: Optional[str] = None,
    ) -> Optional[TraceDetailWithTimeline]:
        """获取对话详情（带时间线）."""
        trace = await self.get_trace(trace_id, source_id)
        if trace is None:
            return None

        spans = await self.get_spans(trace_id)

        # 从 ES 获取 model_output
        from ...database.elasticsearch import get_es_client

        es_client = get_es_client()
        if es_client and es_client.is_connected:
            trace.model_output = await es_client.get_message(trace_id)

        feedback = await self.get_trace_feedback(trace_id, trace.source_id)
        timeline = self._build_timeline(spans)
        skill_invocations = self._build_skill_invocations(spans)

        llm_duration = sum(
            s.duration_ms or 0
            for s in spans
            if s.event_type in (EventType.LLM_INPUT, EventType.LLM_OUTPUT)
        )
        tool_duration = sum(
            s.duration_ms or 0
            for s in spans
            if s.event_type
            in (EventType.TOOL_CALL_START, EventType.TOOL_CALL_END)
        )
        skill_duration = sum(inv.duration_ms for inv in skill_invocations)

        return TraceDetailWithTimeline(
            trace=trace,
            feedback=feedback,
            spans=spans,
            timeline=timeline,
            skill_invocations=skill_invocations,
            llm_duration_ms=llm_duration,
            tool_duration_ms=tool_duration,
            skill_duration_ms=skill_duration,
            total_skills=len(skill_invocations),
            total_tools=len(
                [s for s in spans if s.event_type == EventType.TOOL_CALL_END],
            ),
            total_llm_calls=len(
                [s for s in spans if s.event_type == EventType.LLM_INPUT],
            ),
        )

    # ===== 用户消息 =====

    async def get_user_messages(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        query_text: Optional[str] = None,
        export: bool = False,
        bbk_ids: Optional[str] = None,
    ) -> tuple[list[UserMessageItem], int]:
        """获取用户消息列表."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now()

        if source_id == "all":
            where_clauses = [
                "start_time >= %s",
                "start_time <= %s",
            ]
            params: list[Any] = [start_date, end_date]
        else:
            where_clauses = [
                "source_id = %s",
                "start_time >= %s",
                "start_time <= %s",
            ]
            params = [source_id, start_date, end_date]

        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        if session_id:
            where_clauses.append("session_id = %s")
            params.append(session_id)
        if query_text:
            where_clauses.append("user_message LIKE %s")
            params.append(f"%{query_text}%")
        if bbk_ids:
            bbk_filter_sql, bbk_params = build_bbk_in_filter(bbk_ids)
            where_clauses.append(
                f"bbk_id IN ({', '.join(['%s'] * len(bbk_params))})",
            )
            params.extend(bbk_params)

        where_sql = " AND ".join(where_clauses)

        count_query = f"SELECT COUNT(*) as total FROM swe_tracing_traces WHERE {where_sql}"
        count_row = await self._db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        if export:
            sql_query = f"""
                SELECT t.trace_id, t.source_id, t.user_id, t.session_id, t.channel, t.user_message,
                       t.model_name,
                       t.start_time, t.duration_ms,
                       COALESCE(t.user_name, (
                           SELECT t2.user_name FROM swe_tracing_traces t2
                           WHERE t2.user_id = t.user_id AND t2.user_name IS NOT NULL
                           ORDER BY t2.start_time DESC LIMIT 1
                       )) as user_name,
                       COALESCE(t.bbk_id, (
                           SELECT t3.bbk_id FROM swe_tracing_traces t3
                           WHERE t3.user_id = t.user_id AND t3.bbk_id IS NOT NULL
                           ORDER BY t3.start_time DESC LIMIT 1
                       )) as bbk_id
                FROM swe_tracing_traces t
                WHERE {where_sql}
                ORDER BY t.start_time DESC
            """
            rows = await self._db.fetch_all(sql_query, tuple(params))
        else:
            offset = (page - 1) * page_size
            sql_query = f"""
                SELECT t.trace_id, t.source_id, t.user_id, t.session_id, t.channel, t.user_message,
                       t.model_name,
                       t.start_time, t.duration_ms,
                       COALESCE(t.user_name, (
                           SELECT t2.user_name FROM swe_tracing_traces t2
                           WHERE t2.user_id = t.user_id AND t2.user_name IS NOT NULL
                           ORDER BY t2.start_time DESC LIMIT 1
                       )) as user_name,
                       COALESCE(t.bbk_id, (
                           SELECT t3.bbk_id FROM swe_tracing_traces t3
                           WHERE t3.user_id = t.user_id AND t3.bbk_id IS NOT NULL
                           ORDER BY t3.start_time DESC LIMIT 1
                       )) as bbk_id
                FROM swe_tracing_traces t
                WHERE {where_sql}
                ORDER BY t.start_time DESC
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])
            rows = await self._db.fetch_all(sql_query, tuple(params))

        messages = [
            UserMessageItem(
                trace_id=row["trace_id"],
                source_id=row["source_id"],
                user_id=row["user_id"],
                user_name=row["user_name"],
                bbk_id=row["bbk_id"],
                session_id=row["session_id"],
                channel=row["channel"],
                user_message=row["user_message"],
                model_name=row["model_name"],
                start_time=row["start_time"],
                duration_ms=row["duration_ms"],
            )
            for row in rows
        ]
        return messages, total

    # ===== 辅助方法 =====

    def _build_timeline(self, spans: list[Span]) -> list[TimelineEvent]:
        """构建时间线（只展示技能调用和LLM调用）."""
        spans = sorted(spans, key=lambda s: s.start_time)

        timeline: list[TimelineEvent] = []
        skill_stack: list[TimelineEvent] = []

        for span in spans:
            if span.event_type == EventType.SKILL_INVOCATION:
                event = TimelineEvent(
                    event_type="skill_invocation",
                    span_id=span.span_id,
                    start_time=span.start_time,
                    end_time=span.end_time,
                    duration_ms=span.duration_ms or 0,
                    skill_name=span.skill_name,
                    confidence=1.0,
                    trigger_reason="declared",
                    children=[],
                )

                if skill_stack:
                    skill_stack[-1].children.append(event)
                else:
                    timeline.append(event)

                skill_stack.append(event)

            elif span.event_type == EventType.SKILL_END:
                # 技能结束时弹出栈
                if skill_stack:
                    skill_stack.pop()

            elif span.event_type == EventType.LLM_INPUT:
                event = TimelineEvent(
                    event_type="llm_call",
                    span_id=span.span_id,
                    start_time=span.start_time,
                    end_time=span.end_time,
                    duration_ms=span.duration_ms or 0,
                    model_name=span.model_name,
                    input_tokens=span.input_tokens,
                    output_tokens=span.output_tokens,
                    children=[],
                )

                if skill_stack:
                    skill_stack[-1].children.append(event)
                else:
                    timeline.append(event)

        return timeline

    def _build_skill_invocations(
        self,
        spans: list[Span],
    ) -> list[SkillCallTimeline]:
        """构建技能调用摘要."""
        skill_spans = [
            s for s in spans if s.event_type == EventType.SKILL_INVOCATION
        ]

        invocations: list[SkillCallTimeline] = []
        skill_tools: dict[str, list[ToolCallInSkill]] = {}

        for span in spans:
            if span.event_type == EventType.TOOL_CALL_END and span.skill_name:
                skill_name = span.skill_name
                if skill_name not in skill_tools:
                    skill_tools[skill_name] = []

                skill_tools[skill_name].append(
                    ToolCallInSkill(
                        span_id=span.span_id,
                        tool_name=span.tool_name or "",
                        mcp_server=span.mcp_server,
                        start_time=span.start_time,
                        end_time=span.end_time,
                        duration_ms=span.duration_ms or 0,
                        status="error" if span.error else "success",
                        error=span.error,
                        skill_weight=None,
                    ),
                )

        for skill_span in skill_spans:
            skill_name = skill_span.skill_name or ""
            tools = skill_tools.get(skill_name, [])

            invocations.append(
                SkillCallTimeline(
                    span_id=skill_span.span_id,
                    skill_name=skill_name,
                    start_time=skill_span.start_time,
                    end_time=skill_span.end_time,
                    duration_ms=skill_span.duration_ms or 0,
                    confidence=1.0,
                    trigger_reason="declared",
                    tools=tools,
                    total_tool_calls=len(tools),
                    tool_duration_ms=sum(t.duration_ms for t in tools),
                ),
            )

        return invocations

    def _row_to_trace(self, row: dict) -> Trace:
        """转换数据库行为 Trace 模型."""
        return Trace(
            trace_id=row["trace_id"],
            source_id=row["source_id"],
            user_id=row["user_id"],
            user_name=row.get("user_name"),
            bbk_id=row.get("bbk_id"),
            session_id=row["session_id"],
            channel=row["channel"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            duration_ms=row["duration_ms"],
            model_name=row["model_name"],
            total_input_tokens=row["total_input_tokens"] or 0,
            total_output_tokens=row["total_output_tokens"] or 0,
            tools_used=(
                json.loads(row["tools_used"]) if row["tools_used"] else []
            ),
            skills_used=(
                json.loads(row["skills_used"]) if row["skills_used"] else []
            ),
            status=(
                TraceStatus(row["status"])
                if row["status"]
                else TraceStatus.RUNNING
            ),
            error=row["error"],
            user_message=row.get("user_message"),
        )

    def _row_to_span(self, row: dict) -> Span:
        """转换数据库行为 Span 模型."""
        return Span(
            span_id=row["span_id"],
            trace_id=row["trace_id"],
            source_id=row["source_id"],
            name=row["name"],
            event_type=EventType(row["event_type"]),
            start_time=row["start_time"],
            end_time=row["end_time"],
            duration_ms=row["duration_ms"],
            user_id=row.get("user_id") or "",
            user_name=row.get("user_name"),
            bbk_id=row.get("bbk_id"),
            session_id=row.get("session_id") or "",
            channel=row.get("channel") or "",
            model_name=row["model_name"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            tool_name=row["tool_name"],
            skill_name=row["skill_name"],
            mcp_server=row.get("mcp_server"),
            tool_input=(
                json.loads(row["tool_input"]) if row["tool_input"] else None
            ),
            tool_output=row["tool_output"],
            error=row["error"],
        )
