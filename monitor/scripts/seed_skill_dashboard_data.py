# -*- coding: utf-8 -*-
"""生成近三个月运营看板技能数据。

数据来源:
    - swe_skills: 提供 skill_id 的稳定展示名
    - swe_marketplace_skills: 提供可纳入统计的 source_id / skill_id

生成内容:
    - swe_tracing_traces
    - swe_tracing_spans

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_skill_dashboard_data.py
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from swe.envs import load_envs_into_environ

load_envs_into_environ()

from swe.database import DatabaseConnection, get_database_config

SEED_PREFIX = "seed-skill-dashboard-"
DEFAULT_SOURCE_ID = "RMASSIST"
DEFAULT_DAYS = 90

BBK_IDS = ["100", "200", "201", "202", "203", "204", "205", "206", "V00"]
TENANT_USERS = [
    {
        "tenant_id": f"user-{10000 + index:05d}",
        "tenant_name": name,
        "bbk_id": BBK_IDS[index % len(BBK_IDS)],
    }
    for index, name in enumerate(
        [
            "张三",
            "李四",
            "王五",
            "赵六",
            "钱七",
            "孙八",
            "周九",
            "吴十",
            "郑一",
            "陈明",
            "林敏",
            "何强",
            "许洁",
            "冯磊",
            "高宁",
            "马超",
            "罗欣",
            "宋佳",
            "唐伟",
            "韩雪",
        ]
        * 8,
    )
]
CHANNELS = ["web", "console", "api", "mobile"]
MODELS = ["gpt-4.1", "gpt-4o", "claude-3.7", "qwen2.5"]
TOOLS = [
    "sql_query",
    "file_read",
    "python_executor",
    "web_search",
    "chart_generator",
    "report_builder",
    "data_validator",
    "notification_sender",
]
CRON_JOB_NAMES = [
    "技能看板任务",
    "客户画像更新",
    "营销推荐生成",
    "合规检查任务",
    "报表汇总任务",
    "风险扫描任务",
    "客户回访提醒",
    "数据质量校验",
]
BUTTON_TYPES = ["plan", "insight", "phone"]
BUTTON_WEIGHTS = [50, 32, 18]
BUTTON_NAMES = {
    "plan": ["计划", "查看计划", "计划详情"],
    "insight": ["洞察", "查看洞察", "洞察详情"],
    "phone": ["电访", "电话访问", "拨打电话"],
}

CLICK_EVENT_COLUMNS = {
    "event_id": "VARCHAR(128) NULL COMMENT '点击事件ID'",
    "source_id": "VARCHAR(64) NULL COMMENT '来源标识'",
    "user_id": "VARCHAR(128) NULL COMMENT '点击用户标识'",
    "bbk_id": "VARCHAR(128) NULL COMMENT '分行/机构标识'",
    "cron_task_id": "VARCHAR(128) NULL COMMENT '定时任务ID'",
    "cron_task_name": "VARCHAR(255) NULL COMMENT '定时任务名称'",
    "file_url": "TEXT NULL COMMENT 'HTML 文件链接'",
    "file_name": "VARCHAR(512) NULL COMMENT 'HTML 文件名'",
    "list_key": "VARCHAR(1024) NULL COMMENT '名单稳定标识'",
    "list_name": "VARCHAR(512) NULL COMMENT '名单展示名称'",
    "button_id": "VARCHAR(255) NULL COMMENT '按钮稳定标识'",
    "button_name": "VARCHAR(255) NULL COMMENT '按钮展示名称'",
    "button_text": "VARCHAR(512) NULL COMMENT '按钮文本兜底'",
    "button_type": "VARCHAR(32) NULL COMMENT '按钮类型'",
    "customer_id": "VARCHAR(128) NULL COMMENT '客户唯一标识'",
    "customer_name": "VARCHAR(255) NULL COMMENT '客户展示名称'",
    "customer_info": "JSON NULL COMMENT '客户扩展信息'",
    "clicked_at": "DATETIME NULL COMMENT '前端点击时间'",
}

CLICK_EVENT_INDEXES = {
    "idx_clicked_at": "CREATE INDEX idx_clicked_at ON swe_html_preview_click_events (clicked_at)",
    "idx_task_clicked": "CREATE INDEX idx_task_clicked ON swe_html_preview_click_events (cron_task_id, clicked_at)",
    "idx_button_type_clicked": "CREATE INDEX idx_button_type_clicked ON swe_html_preview_click_events (button_type, clicked_at)",
    "idx_source_clicked": "CREATE INDEX idx_source_clicked ON swe_html_preview_click_events (source_id, clicked_at)",
}

TENANT_INIT_COLUMNS = {
    "tenant_id": "VARCHAR(128) NOT NULL COMMENT '租户ID'",
    "source_id": "VARCHAR(128) NOT NULL COMMENT '来源标识'",
    "tenant_name": "VARCHAR(255) NULL COMMENT '租户名称'",
    "bbk_id": "VARCHAR(64) NULL COMMENT '机构标识'",
    "init_source": "VARCHAR(128) NOT NULL DEFAULT 'default' COMMENT '初始化模板来源'",
    "tenant_type": "VARCHAR(32) NOT NULL DEFAULT 'tenant' COMMENT '租户类型'",
    "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'",
    "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'",
}


def _pick_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback


async def _load_skill_catalog(db) -> dict[str, dict[str, str]]:
    """加载 swe_skills 的稳定 skill_id 展示映射。"""
    rows = await db.fetch_all(
        """
        SELECT skill_id, skill_name, cn_name
        FROM (
            SELECT skill_id, skill_name, cn_name,
                   ROW_NUMBER() OVER (
                       PARTITION BY skill_id
                       ORDER BY
                           CASE
                               WHEN cn_name IS NOT NULL
                                    AND TRIM(cn_name) <> ''
                               THEN 0 ELSE 1 END ASC,
                           CASE WHEN enabled = 1 THEN 0 ELSE 1 END ASC,
                           updated_at DESC,
                           id DESC
                   ) AS rn
            FROM swe_skills
            WHERE skill_id IS NOT NULL AND TRIM(skill_id) <> ''
        ) ranked
        WHERE rn = 1
        """,
    )
    return {
        row["skill_id"]: {
            "skill_name": _pick_text(row.get("skill_name"), row["skill_id"]),
            "cn_name": _pick_text(
                row.get("cn_name"),
                row.get("skill_name") or row["skill_id"],
            ),
        }
        for row in rows
    }


async def _load_source_skill_map(
    db,
    skill_catalog: dict[str, dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """按 source_id 读取可纳入统计的技能。"""
    rows = await db.fetch_all(
        """
        SELECT source_id, skill_id, skill_name, cn_name
        FROM swe_marketplace_skills
        WHERE include_in_statistics = 1
          AND source_id IS NOT NULL
          AND TRIM(source_id) <> ''
          AND source_id <> 'default'
        ORDER BY source_id, skill_id
        """,
    )
    source_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        source_id = _pick_text(row.get("source_id"), DEFAULT_SOURCE_ID)
        skill_id = _pick_text(row.get("skill_id"), "")
        skill_info = skill_catalog.get(skill_id, {})
        skill_name = _pick_text(
            row.get("skill_name") or skill_info.get("skill_name"),
            skill_id or "skill",
        )
        cn_name = _pick_text(
            row.get("cn_name") or skill_info.get("cn_name"),
            skill_name,
        )
        if not skill_id:
            continue
        source_map[source_id].append(
            {
                "skill_id": skill_id,
                "skill_name": skill_name,
                "cn_name": cn_name,
            },
        )

    if source_map:
        return source_map

    # 如果市场技能表为空，退化为把所有技能挂到默认 source。
    fallback = [
        {
            "skill_id": skill_id,
            "skill_name": info["skill_name"],
            "cn_name": info["cn_name"],
        }
        for skill_id, info in skill_catalog.items()
    ]
    if fallback:
        source_map[DEFAULT_SOURCE_ID] = fallback
    return source_map


async def _ensure_tenant_init_source_schema(db) -> None:
    """确保租户来源表存在并包含运行时需要的字段。"""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS swe_tenant_init_source (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            tenant_id VARCHAR(128) NOT NULL COMMENT '租户ID',
            source_id VARCHAR(128) NOT NULL COMMENT '来源标识',
            tenant_name VARCHAR(255) NULL COMMENT '租户名称',
            bbk_id VARCHAR(64) NULL COMMENT '机构标识',
            init_source VARCHAR(128) NOT NULL DEFAULT 'default'
                COMMENT '初始化模板来源',
            tenant_type VARCHAR(32) NOT NULL DEFAULT 'tenant'
                COMMENT '租户类型',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                COMMENT '创建时间',
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_tenant_source (tenant_id, source_id),
            INDEX idx_source_tenant_type (source_id, tenant_type),
            INDEX idx_source_bbk (source_id, bbk_id),
            INDEX idx_tenant_prefix (tenant_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    )
    rows = await db.fetch_all(
        """
        SELECT COLUMN_NAME
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'swe_tenant_init_source'
        """,
    )
    existing = {row["COLUMN_NAME"] for row in rows}
    for column_name, column_sql in TENANT_INIT_COLUMNS.items():
        if column_name not in existing:
            await db.execute(
                f"ALTER TABLE swe_tenant_init_source ADD COLUMN {column_name} {column_sql}",
            )
    for index_sql in [
        "CREATE UNIQUE INDEX uk_tenant_source ON swe_tenant_init_source (tenant_id, source_id)",
        "CREATE INDEX idx_source_tenant_type ON swe_tenant_init_source (source_id, tenant_type)",
        "CREATE INDEX idx_source_bbk ON swe_tenant_init_source (source_id, bbk_id)",
    ]:
        try:
            await db.execute(index_sql)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if "duplicate" not in message and "exists" not in message:
                raise


async def _seed_tenant_init_sources(
    db,
    source_map: dict[str, list[dict[str, str]]],
) -> int:
    """按 source_id 初始化看板用户来源数据。"""
    await _ensure_tenant_init_source_schema(db)
    rows: list[tuple[Any, ...]] = []
    for source_id in sorted(source_map):
        init_source = f"default_{source_id}"
        rows.append(
            (
                init_source,
                source_id,
                f"{source_id}模板",
                None,
                "default",
                "template",
            ),
        )
        for tenant in TENANT_USERS:
            rows.append(
                (
                    tenant["tenant_id"],
                    source_id,
                    tenant["tenant_name"],
                    tenant["bbk_id"],
                    init_source,
                    "tenant",
                ),
            )
    await db.execute_many(
        """
        INSERT INTO swe_tenant_init_source (
            tenant_id, source_id, tenant_name, bbk_id,
            init_source, tenant_type
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s
        )
        ON DUPLICATE KEY UPDATE
            tenant_name = VALUES(tenant_name),
            bbk_id = VALUES(bbk_id),
            init_source = VALUES(init_source),
            tenant_type = VALUES(tenant_type),
            updated_at = CURRENT_TIMESTAMP
        """,
        rows,
    )
    return len(rows)


def _make_trace_row(
    *,
    trace_id: str,
    source_id: str,
    skill: dict[str, str],
    start_time: datetime,
    user_id: str,
    user_name: str,
    bbk_id: str,
    session_id: str,
) -> tuple[Any, ...]:
    duration_ms = random.randint(800, 24000)
    model_name = random.choice(MODELS)
    input_tokens = random.randint(120, 4200)
    output_tokens = random.randint(60, 1600)
    total_tokens = input_tokens + output_tokens
    status = random.choices(
        ["success", "error", "cancelled"],
        weights=[0.84, 0.11, 0.05],
        k=1,
    )[0]
    end_time = start_time + timedelta(milliseconds=duration_ms)
    user_message_pool = [
        "帮我分析客户画像",
        "生成本周业务报表",
        "查询最近异常记录",
        "检查合规风险",
        "输出营销推荐方案",
        "生成图表并解释结果",
        "汇总近三个月趋势",
    ]
    user_message = random.choice(user_message_pool)
    return (
        trace_id,
        None,
        source_id,
        user_id,
        session_id,
        user_name,
        random.choice(CHANNELS),
        start_time,
        end_time,
        duration_ms,
        model_name,
        input_tokens,
        output_tokens,
        total_tokens,
        json.dumps([skill["skill_name"]], ensure_ascii=False),
        json.dumps([skill["skill_id"]], ensure_ascii=False),
        status,
        "模拟错误信息" if status == "error" else None,
        user_message,
        user_name,
        bbk_id,
    )


def _make_skill_span_row(
    *,
    span_id: str,
    trace_id: str,
    source_id: str,
    skill: dict[str, str],
    start_time: datetime,
    duration_ms: int,
    user_id: str,
    user_name: str,
    bbk_id: str,
    session_id: str,
) -> tuple[Any, ...]:
    return (
        span_id,
        trace_id,
        source_id,
        skill["skill_name"],
        "skill_invocation",
        start_time,
        start_time + timedelta(milliseconds=duration_ms),
        duration_ms,
        user_id,
        session_id,
        random.choice(CHANNELS),
        random.choice(MODELS),
        0,
        0,
        None,
        skill["skill_name"],
        skill["skill_id"],
        None,
        json.dumps(
            {
                "skill_id": skill["skill_id"],
                "skill_name": skill["skill_name"],
                "cn_name": skill["cn_name"],
            },
            ensure_ascii=False,
        ),
        json.dumps({"result": "ok"}, ensure_ascii=False),
        None,
        user_name,
        bbk_id,
    )


def _make_tool_span_row(
    *,
    span_id: str,
    trace_id: str,
    source_id: str,
    skill: dict[str, str],
    start_time: datetime,
    duration_ms: int,
    user_id: str,
    user_name: str,
    bbk_id: str,
    session_id: str,
) -> tuple[Any, ...]:
    tool_name = random.choice(TOOLS)
    tool_duration = random.randint(300, 12000)
    return (
        span_id,
        trace_id,
        source_id,
        tool_name,
        "tool_call_end",
        start_time,
        start_time + timedelta(milliseconds=tool_duration),
        tool_duration,
        user_id,
        session_id,
        random.choice(CHANNELS),
        random.choice(MODELS),
        random.randint(10, 1800),
        random.randint(5, 1200),
        tool_name,
        skill["skill_name"],
        skill["skill_id"],
        random.choice(
            ["mysql_server", "redis_server", "elasticsearch_server", None],
        ),
        json.dumps(
            {"tool": tool_name, "skill_id": skill["skill_id"]},
            ensure_ascii=False,
        ),
        json.dumps(
            {"ok": True, "rows": random.randint(0, 20)},
            ensure_ascii=False,
        ),
        None,
        user_name,
        bbk_id,
    )


async def _seed_data(
    db,
    source_map: dict[str, list[dict[str, str]]],
) -> tuple[int, int, int]:
    """生成近三个月的 trace / span 数据。"""
    await db.execute(
        f"DELETE FROM swe_tracing_spans WHERE span_id LIKE '{SEED_PREFIX}%'",
    )
    await db.execute(
        f"DELETE FROM swe_tracing_traces WHERE trace_id LIKE '{SEED_PREFIX}%'",
    )

    trace_rows: list[tuple[Any, ...]] = []
    span_rows: list[tuple[Any, ...]] = []
    trace_count = 0
    span_count = 0
    daily_skill_rows = 0

    start_day = datetime.now().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ) - timedelta(days=DEFAULT_DAYS - 1)
    end_day = datetime.now()

    source_ids = sorted(source_map)

    current_day = start_day.date()
    while current_day <= end_day.date():
        is_weekend = current_day.weekday() >= 5
        base_daily = (
            random.randint(24, 48)
            if not is_weekend
            else random.randint(10, 20)
        )
        for source_id in source_ids:
            skills = source_map[source_id]
            if not skills:
                continue
            daily_count = max(
                8,
                int(base_daily * (0.8 + random.random() * 0.8)),
            )
            daily_skill_rows += daily_count

            for _ in range(daily_count):
                skill = random.choice(skills)
                trace_id = f"{SEED_PREFIX}{uuid.uuid4().hex}"
                span_id = f"{SEED_PREFIX}{uuid.uuid4().hex[:24]}"
                tenant = random.choice(TENANT_USERS)
                user_id = tenant["tenant_id"]
                user_name = tenant["tenant_name"]
                bbk_id = tenant["bbk_id"]
                session_id = f"{SEED_PREFIX}{uuid.uuid4().hex[:16]}"
                start_time = datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    random.choices(
                        [random.randint(9, 18), random.randint(0, 23)],
                        weights=[75, 25],
                        k=1,
                    )[0],
                    random.randint(0, 59),
                    random.randint(0, 59),
                )

                trace_row = _make_trace_row(
                    trace_id=trace_id,
                    source_id=source_id,
                    skill=skill,
                    start_time=start_time,
                    user_id=user_id,
                    user_name=user_name,
                    bbk_id=bbk_id,
                    session_id=session_id,
                )
                trace_rows.append(trace_row)
                trace_count += 1

                skill_duration = random.randint(800, 16000)
                span_rows.append(
                    _make_skill_span_row(
                        span_id=span_id,
                        trace_id=trace_id,
                        source_id=source_id,
                        skill=skill,
                        start_time=start_time,
                        duration_ms=skill_duration,
                        user_id=user_id,
                        user_name=user_name,
                        bbk_id=bbk_id,
                        session_id=session_id,
                    ),
                )
                span_count += 1

                if random.random() < 0.78:
                    span_rows.append(
                        _make_tool_span_row(
                            span_id=f"{SEED_PREFIX}{uuid.uuid4().hex[:24]}",
                            trace_id=trace_id,
                            source_id=source_id,
                            skill=skill,
                            start_time=start_time
                            + timedelta(milliseconds=skill_duration // 2),
                            duration_ms=skill_duration,
                            user_id=user_id,
                            user_name=user_name,
                            bbk_id=bbk_id,
                            session_id=session_id,
                        ),
                    )
                    span_count += 1

                if len(trace_rows) >= 300:
                    await db.execute_many(
                        """
                        INSERT INTO swe_tracing_traces (
                            trace_id, b3_trace_id, source_id, user_id,
                            session_id, session_name, channel, start_time,
                            end_time, duration_ms, model_name,
                            total_input_tokens, total_output_tokens,
                            total_tokens, tools_used, skills_used,
                            status, error, user_message, user_name, bbk_id
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        """,
                        trace_rows,
                    )
                    trace_rows = []

                if len(span_rows) >= 300:
                    await db.execute_many(
                        """
                        INSERT INTO swe_tracing_spans (
                            span_id, trace_id, source_id, name, event_type,
                            start_time, end_time, duration_ms, user_id,
                            session_id, channel, model_name, input_tokens,
                            output_tokens, tool_name, skill_name, skill_id,
                            mcp_server, tool_input, tool_output, error,
                            user_name, bbk_id
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s
                        )
                        """,
                        span_rows,
                    )
                    span_rows = []

        current_day += timedelta(days=1)

    if trace_rows:
        await db.execute_many(
            """
            INSERT INTO swe_tracing_traces (
                trace_id, b3_trace_id, source_id, user_id,
                session_id, session_name, channel, start_time,
                end_time, duration_ms, model_name,
                total_input_tokens, total_output_tokens,
                total_tokens, tools_used, skills_used,
                status, error, user_message, user_name, bbk_id
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            trace_rows,
        )

    if span_rows:
        await db.execute_many(
            """
            INSERT INTO swe_tracing_spans (
                span_id, trace_id, source_id, name, event_type,
                start_time, end_time, duration_ms, user_id,
                session_id, channel, model_name, input_tokens,
                output_tokens, tool_name, skill_name, skill_id,
                mcp_server, tool_input, tool_output, error,
                user_name, bbk_id
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            )
            """,
            span_rows,
        )

    return trace_count, span_count, daily_skill_rows


def _pick_jobs_per_source(
    source_map: dict[str, list[dict[str, str]]],
) -> dict[str, list[dict[str, Any]]]:
    """按 source_id 生成一组可用于看板的定时任务。"""
    jobs_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_id, skills in source_map.items():
        sample_size = min(
            len(skills),
            max(1, min(max(4, len(skills) // 3), 10)),
        )
        selected_skills = random.sample(skills, sample_size)
        for skill in selected_skills:
            job_id = f"{SEED_PREFIX}{uuid.uuid4().hex[:20]}"
            tenant = random.choice(TENANT_USERS)
            jobs_by_source[source_id].append(
                {
                    "id": job_id,
                    "name": f"{random.choice(CRON_JOB_NAMES)}-{skill['cn_name'][:8]}",
                    "tenant_id": tenant["tenant_id"],
                    "tenant_name": tenant["tenant_name"],
                    "bbk_id": tenant["bbk_id"],
                    "source_id": source_id,
                    "task_type": random.choice(["text", "agent"]),
                    "channel": "web",
                    "target_user_id": tenant["tenant_id"],
                    "skill_id": skill["skill_id"],
                    "skill_ids": skill["skill_id"],
                    "skill_name": skill["skill_name"],
                    "cn_name": skill["cn_name"],
                    "job_origin": "manual",
                },
            )
    return jobs_by_source


async def _seed_cron_data(
    db,
    jobs_by_source: dict[str, list[dict[str, Any]]],
) -> tuple[int, int]:
    """生成近三个月定时任务与执行记录。"""
    await db.execute(
        f"DELETE FROM swe_cron_executions WHERE job_id LIKE '{SEED_PREFIX}%'",
    )
    await db.execute(
        f"DELETE FROM swe_cron_jobs WHERE id LIKE '{SEED_PREFIX}%'",
    )

    job_rows: list[tuple[Any, ...]] = []
    exec_rows: list[tuple[Any, ...]] = []
    job_count = 0
    exec_count = 0

    for source_id, jobs in jobs_by_source.items():
        for job in jobs:
            job_rows.append(
                (
                    job["id"],
                    job["name"],
                    job["tenant_id"],
                    job["tenant_name"],
                    job["bbk_id"],
                    job["source_id"],
                    1,
                    job["task_type"],
                    "0 9 * * *",
                    "Asia/Shanghai",
                    job["channel"],
                    job["target_user_id"],
                    7200,
                    job["skill_ids"],
                    job["job_origin"],
                    "",
                    "active",
                    datetime.now(),
                ),
            )
            job_count += 1

            current_day = (
                datetime.now().replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                - timedelta(days=DEFAULT_DAYS - 1)
            ).date()
            end_day = datetime.now().date()
            while current_day <= end_day:
                is_weekend = current_day.weekday() >= 5
                daily_execs = (
                    random.randint(1, 3)
                    if not is_weekend
                    else random.randint(0, 2)
                )
                for _ in range(daily_execs):
                    tenant = random.choice(TENANT_USERS)
                    actual_time = datetime(
                        current_day.year,
                        current_day.month,
                        current_day.day,
                        random.randint(6, 22),
                        random.randint(0, 59),
                        random.randint(0, 59),
                    )
                    duration_ms = random.randint(800, 42000)
                    end_time = actual_time + timedelta(
                        milliseconds=duration_ms,
                    )
                    status = random.choices(
                        [
                            "success",
                            "error",
                            "timeout",
                            "cancelled",
                            "skipped",
                        ],
                        weights=[82, 8, 4, 3, 3],
                        k=1,
                    )[0]
                    is_read = (
                        1
                        if status == "success" and random.random() < 0.72
                        else 0
                    )
                    read_at = end_time if is_read else None
                    exec_rows.append(
                        (
                            job["id"],
                            job["name"],
                            tenant["tenant_id"],
                            actual_time,
                            actual_time,
                            end_time,
                            duration_ms,
                            status,
                            (
                                "模拟错误信息"
                                if status in ("error", "timeout")
                                else ""
                            ),
                            uuid.uuid4().hex[:12],
                            f"{SEED_PREFIX}{uuid.uuid4().hex[:24]}",
                            f"{SEED_PREFIX}{uuid.uuid4().hex[:16]}",
                            is_read,
                            read_at,
                            actual_time,
                        ),
                    )
                    exec_count += 1
                current_day += timedelta(days=1)
            current_day = (
                datetime.now().replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                - timedelta(days=DEFAULT_DAYS - 1)
            ).date()

    if job_rows:
        await db.execute_many(
            """
            INSERT INTO swe_cron_jobs (
                id, name, tenant_id, tenant_name, bbk_id, source_id,
                enabled, task_type, cron_expr, timezone, channel,
                target_user_id, timeout_seconds, skill_ids, job_origin,
                subscription_key, status, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
            """,
            job_rows,
        )

    if exec_rows:
        await db.execute_many(
            """
            INSERT INTO swe_cron_executions (
                job_id, job_name, tenant_id, scheduled_time, actual_time,
                end_time, duration_ms, status, error_message, instance_id,
                trace_id, session_id, is_read, read_at, created_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            exec_rows,
        )

    return job_count, exec_count


async def _ensure_click_event_schema(db) -> None:
    """补齐 HTML 预览点击事件表的运营看板字段。"""
    rows = await db.fetch_all(
        """
        SELECT COLUMN_NAME
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'swe_html_preview_click_events'
        """,
    )
    existing = {row["COLUMN_NAME"] for row in rows}
    for column_name, column_sql in CLICK_EVENT_COLUMNS.items():
        if column_name not in existing:
            await db.execute(
                f"ALTER TABLE swe_html_preview_click_events ADD COLUMN {column_name} {column_sql}",
            )
    for _, index_sql in CLICK_EVENT_INDEXES.items():
        try:
            await db.execute(index_sql)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if "duplicate" not in message and "exists" not in message:
                raise


async def _seed_click_data(
    db,
    jobs_by_source: dict[str, list[dict[str, Any]]],
) -> int:
    """生成 HTML 预览点击事件。"""
    await db.execute(
        f"DELETE FROM swe_html_preview_click_events WHERE cron_task_id LIKE '{SEED_PREFIX}%'",
    )

    click_rows: list[tuple[Any, ...]] = []
    click_count = 0
    start_day = datetime.now().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ) - timedelta(days=DEFAULT_DAYS - 1)
    end_day = datetime.now().date()
    current_day = start_day.date()

    customer_names = ["张三", "李四", "王五", "赵六", "钱七", "孙八", "周九"]

    while current_day <= end_day:
        is_weekend = current_day.weekday() >= 5
        for source_id, jobs in jobs_by_source.items():
            if not jobs:
                continue
            daily_clicks = (
                random.randint(12, 30)
                if not is_weekend
                else random.randint(4, 12)
            )
            for _ in range(daily_clicks):
                job = random.choice(jobs)
                tenant = random.choice(TENANT_USERS)
                button_type = random.choices(
                    BUTTON_TYPES,
                    weights=BUTTON_WEIGHTS,
                    k=1,
                )[0]
                button_name = random.choice(BUTTON_NAMES[button_type])
                clicked_at = datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    random.randint(8, 21),
                    random.randint(0, 59),
                    random.randint(0, 59),
                )
                customer_id = f"CUST-{random.randint(10000, 99999)}"
                customer_name = random.choice(customer_names)
                click_rows.append(
                    (
                        f"{SEED_PREFIX}{uuid.uuid4().hex[:24]}",
                        source_id,
                        tenant["tenant_id"],
                        tenant["bbk_id"],
                        job["id"],
                        job["name"],
                        f"https://example.com/{job['id']}.html",
                        f"{job['name']}.html",
                        f"{job['skill_id']}",
                        job["cn_name"],
                        f"btn-{uuid.uuid4().hex[:8]}",
                        button_name,
                        button_name,
                        button_type,
                        customer_id,
                        customer_name,
                        json.dumps(
                            {
                                "客户姓名": customer_name,
                                "客户编号": customer_id,
                                "skill_id": job["skill_id"],
                            },
                            ensure_ascii=False,
                        ),
                        clicked_at,
                    ),
                )
                click_count += 1
                if len(click_rows) >= 300:
                    await db.execute_many(
                        """
                        INSERT INTO swe_html_preview_click_events (
                            event_id, source_id, user_id, bbk_id, cron_task_id,
                            cron_task_name, file_url, file_name, list_key,
                            list_name, button_id, button_name, button_text,
                            button_type, customer_id, customer_name,
                            customer_info, clicked_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        click_rows,
                    )
                    click_rows = []
        current_day += timedelta(days=1)

    if click_rows:
        await db.execute_many(
            """
            INSERT INTO swe_html_preview_click_events (
                event_id, source_id, user_id, bbk_id, cron_task_id,
                cron_task_name, file_url, file_name, list_key,
                list_name, button_id, button_name, button_text,
                button_type, customer_id, customer_name,
                customer_info, clicked_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            click_rows,
        )

    return click_count


async def _verify(db, source_map: dict[str, list[dict[str, str]]]) -> None:
    """打印插入结果摘要。"""
    total_traces = await db.fetch_one(
        f"SELECT COUNT(*) AS cnt FROM swe_tracing_traces WHERE trace_id LIKE '{SEED_PREFIX}%'",
    )
    total_spans = await db.fetch_one(
        f"SELECT COUNT(*) AS cnt FROM swe_tracing_spans WHERE span_id LIKE '{SEED_PREFIX}%'",
    )
    print("\n=== 统计摘要 ===")
    print(f"trace_count: {total_traces['cnt'] if total_traces else 0}")
    print(f"span_count: {total_spans['cnt'] if total_spans else 0}")
    print(f"source_count: {len(source_map)}")
    tenant_count = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM swe_tenant_init_source WHERE tenant_type = 'tenant'",
    )
    template_count = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM swe_tenant_init_source WHERE tenant_type = 'template'",
    )
    print(f"tenant_count: {tenant_count['cnt'] if tenant_count else 0}")
    print(f"template_count: {template_count['cnt'] if template_count else 0}")

    print("\n=== 近三个月技能排行样例 ===")
    rows = await db.fetch_all(
        """
        SELECT source_id, skill_name, COUNT(*) AS cnt
        FROM swe_tracing_spans
        WHERE trace_id LIKE %s
          AND event_type = 'skill_invocation'
        GROUP BY source_id, skill_name
        ORDER BY cnt DESC
        LIMIT 10
        """,
        (f"{SEED_PREFIX}%",),
    )
    for row in rows:
        print(f"{row['source_id']} | {row['skill_name']}: {row['cnt']}")

    cron_row = await db.fetch_one(
        f"SELECT COUNT(*) AS cnt FROM swe_cron_jobs WHERE id LIKE '{SEED_PREFIX}%'",
    )
    exec_row = await db.fetch_one(
        f"SELECT COUNT(*) AS cnt FROM swe_cron_executions WHERE job_id LIKE '{SEED_PREFIX}%'",
    )
    click_row = await db.fetch_one(
        f"SELECT COUNT(*) AS cnt FROM swe_html_preview_click_events WHERE cron_task_id LIKE '{SEED_PREFIX}%'",
    )
    print("\n=== 运营看板补充数据 ===")
    print(f"cron_jobs: {cron_row['cnt'] if cron_row else 0}")
    print(f"cron_executions: {exec_row['cnt'] if exec_row else 0}")
    print(f"click_events: {click_row['cnt'] if click_row else 0}")


async def main() -> None:
    """主入口。"""
    db_config = get_database_config()
    print(f"数据库: {db_config.host}:{db_config.port}/{db_config.database}")

    db = DatabaseConnection(db_config)
    await db.connect()
    try:
        skill_catalog = await _load_skill_catalog(db)
        source_map = await _load_source_skill_map(db, skill_catalog)
        if not source_map:
            print("未找到可纳入统计的技能，已退出。")
            return

        tenant_rows = await _seed_tenant_init_sources(db, source_map)
        trace_count, span_count, _ = await _seed_data(db, source_map)
        jobs_by_source = _pick_jobs_per_source(source_map)
        job_count, exec_count = await _seed_cron_data(db, jobs_by_source)
        await _ensure_click_event_schema(db)
        click_count = await _seed_click_data(db, jobs_by_source)
        print(f"已插入 tenant_init_source: {tenant_rows}")
        print(f"已插入 trace: {trace_count}, span: {span_count}")
        print(f"已插入 cron_jobs: {job_count}, cron_executions: {exec_count}")
        print(f"已插入 click_events: {click_count}")
        await _verify(db, source_map)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
