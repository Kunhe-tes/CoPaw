# -*- coding: utf-8 -*-
"""向唯一容量调整器提供新协议的已确认运行反馈，不重跑业务。"""

from datetime import timezone

from .executions import RUN_TABLE
from .operations import IDENTITY_FIELDS
from .settlement import ExecutionSettlement, PROTOCOL
from .run_accounting import occupied_run_sql
from .failure_policy import worker_history_join_sql, worker_model_failure_sql

METRICS = (
    "pending_count",
    "claimed_count",
    "running_count",
    "success_count",
    "failure_count",
    "subtask_success_count",
    "subtask_failure_count",
)


def _utc_text(value):
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(" ")


def _scope_filter(scope):
    if scope is None:
        return "", ()
    names = ("source_id", "provider_id", "model_id")
    return (
        " AND " + " AND ".join(f"r.{name}=%s" for name in names),
        tuple(scope[name] for name in names),
    )


class ManagedCapacityFeedback:
    def __init__(self, db):
        self.db = db
        self.settlement = ExecutionSettlement(db)

    async def tick(self):
        return await self.settlement.tick()

    async def scopes(self, *, now_utc, source_ids=None):
        joins = " AND ".join(
            f"r.{name}=d.{name} COLLATE utf8mb4_bin"
            for name in IDENTITY_FIELDS
        )
        source_sql, params = "", [_utc_text(now_utc)]
        if source_ids:
            source_sql = (
                " AND r.source_id IN ("
                + ",".join("%s" for _ in source_ids)
                + ")"
            )
            params.extend(source_ids)
        return await self.db.fetch_all(
            "SELECT DISTINCT r.source_id,r.provider_id,r.model_id "
            f"FROM {RUN_TABLE} r JOIN swe_cron_jobs_v2 d ON {joins} "
            f"WHERE d.management_owner='scheduler' AND {PROTOCOL} "
            "AND ((r.status IN ('queued','dispatch_failed') "
            "AND (r.not_before_at IS NULL OR r.not_before_at<=%s)) "
            f"OR {occupied_run_sql('r')}) "
            + source_sql
            + " ORDER BY r.source_id,r.provider_id,r.model_id",
            params,
        )

    async def summarize(
        self,
        *,
        since,
        now_utc,
        scope=None,
        unused_only=False,
    ):
        clause, params = _scope_filter(scope)
        start, now = _utc_text(since), _utc_text(now_utc)
        state = await self.db.fetch_one(
            "SELECT SUM(CASE WHEN r.status IN ('queued','dispatch_failed') "
            "AND (r.not_before_at IS NULL OR r.not_before_at<=%s) THEN 1 ELSE 0 END) AS pending_count, "
            "SUM(CASE WHEN r.status='dispatching' THEN 1 ELSE 0 END) AS claimed_count, "
            "SUM(CASE WHEN r.status IN ('accepted','running') OR "
            "(r.status='success' AND r.settled_status IS NULL) THEN 1 ELSE 0 END) AS running_count "
            f"FROM {RUN_TABLE} r WHERE {PROTOCOL} "
            f"AND (r.settled_status IS NULL OR r.settled_at>=%s){clause}",
            (now, start, *params),
        )
        model_failure = worker_model_failure_sql()
        main_sample = (
            "r.subtask_success_count IS NULL "
            "AND COALESCE(r.settled_error_code,'')<>'cron_async_subtasks_timeout'"
        )
        expressions = {
            "success_count": (
                f"CASE WHEN {main_sample} AND "
                "(r.settled_status='success' OR "
                f"(r.settled_status='error' AND NOT {model_failure})) "
                "THEN 1 ELSE 0 END"
            ),
            "failure_count": (
                f"CASE WHEN {main_sample} AND r.settled_status='error' "
                f"AND {model_failure} THEN 1 ELSE 0 END"
            ),
            "subtask_success_count": "r.subtask_success_count",
            "subtask_failure_count": "r.subtask_failure_count",
        }
        fields = [
            (
                f"{expression} AS {name}"
                if unused_only
                else f"SUM({expression}) AS {name}"
            )
            for name, expression in expressions.items()
        ]
        if unused_only:
            fields.insert(0, "r.execution_id")
        unused = " AND r.worker_feedback_used=0" if unused_only else ""
        rows = await self.db.fetch_all(
            f"SELECT {', '.join(fields)} FROM {RUN_TABLE} r "
            f"LEFT JOIN swe_cron_executions h ON {worker_history_join_sql()} "
            f"WHERE {PROTOCOL} AND r.settled_at BETWEEN %s AND %s{unused}{clause}",
            (start, now, *params),
        )
        # 跳过的未开始工作、未知 HTTP 回执不伪装成模型执行失败。
        counts = {name: int((state or {}).get(name) or 0) for name in METRICS}
        samples = []
        for row in rows:
            for name in expressions:
                counts[name] += int(row[name] or 0)
            if unused_only and any(row[name] for name in expressions):
                samples.append(row["execution_id"])
        counts["success_count"] += counts["subtask_success_count"]
        counts["failure_count"] += counts["subtask_failure_count"]
        return {
            **counts,
            "latency_p95_ms": 0,
            "feedback_samples": {"managed_runs": samples},
        }
