# -*- coding: utf-8 -*-
"""构造测试数据验证慢查询问题。

线上数据量：
- swe_tracing_traces: 68703 条
- swe_tracing_spans: 1378752 条（约 20 倍于 traces）
- swe_cron_executions: 39146 条
- swe_cron_jobs: 5756 条
"""

import asyncio
import random
import string
import time
from datetime import datetime, timedelta
from typing import Any

import aiomysql

# 数据库连接配置
DB_CONFIG = {
    "host": "120.48.112.239",
    "port": 3306,
    "user": "mysqladmin",
    "password": "123456",
    "db": "rmassistdata",
    "charset": "utf8mb4",
}

# 目标数据量
TARGET_TRACES = 70000
TARGET_SPANS = 1400000  # 约 20 倍于 traces
TARGET_CRON_JOBS = 6000
TARGET_CRON_EXECUTIONS = 40000

# 用户数量（模拟多个用户）
NUM_USERS = 500


def generate_user_id(idx: int) -> str:
    """生成用户 ID。"""
    # 模拟真实用户 ID 格式
    prefixes = ["", "80", "IT", "agent_"]
    prefix = prefixes[idx % len(prefixes)]
    return f"{prefix}user_{idx:04d}"


def generate_trace_id() -> str:
    """生成 trace_id（UUID 格式）。"""
    return "".join(random.choices(string.hexdigits.lower(), k=32))


def generate_session_id() -> str:
    """生成 session_id。"""
    return "".join(random.choices(string.hexdigits.lower(), k=32))


def generate_skill_name(idx: int) -> str:
    """生成技能名称。"""
    skills = [
        "数据分析",
        "报告生成",
        "客户查询",
        "风险评估",
        "合规检查",
        "审批流程",
        "文档处理",
        "消息推送",
        "定时提醒",
        "数据同步",
    ]
    return random.choice(skills)


async def get_existing_counts(conn: aiomysql.Connection) -> dict[str, int]:
    """获取现有数据量。"""
    async with conn.cursor() as cur:
        counts = {}
        for table in [
            "swe_tracing_traces",
            "swe_tracing_spans",
            "swe_cron_jobs",
            "swe_cron_executions",
        ]:
            await cur.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            row = await cur.fetchone()
            counts[table] = row[0]
        return counts


async def insert_traces(
    conn: aiomysql.Connection,
    existing: int,
    target: int,
) -> list[dict[str, Any]]:
    """插入 traces 数据。"""
    if existing >= target:
        print(f"  traces 已有 {existing} 条，跳过插入")
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT trace_id, user_id, session_id, source_id FROM swe_tracing_traces LIMIT 1000",
            )
            rows = await cur.fetchall()
            return [
                {
                    "trace_id": r[0],
                    "user_id": r[1],
                    "session_id": r[2],
                    "source_id": r[3],
                }
                for r in rows
            ]

    to_insert = target - existing
    print(f"  需要插入 {to_insert} 条 traces...")

    user_ids = [generate_user_id(i) for i in range(NUM_USERS)]
    source_ids = ["default", "prod", "test", "dev"]
    channels = ["console", "webhook", "api"]

    traces = []
    batch_size = 1000
    inserted = 0

    base_time = datetime.now() - timedelta(days=30)

    async with conn.cursor() as cur:
        for i in range(to_insert):
            user_id = random.choice(user_ids)
            source_id = random.choice(source_ids)
            session_id = generate_session_id()
            trace_id = generate_trace_id()
            start_time = base_time + timedelta(
                seconds=random.randint(0, 30 * 24 * 3600),
            )

            traces.append(
                {
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "source_id": source_id,
                    "start_time": start_time,
                },
            )

            # 模拟数据
            status = random.choice(
                ["completed", "completed", "completed", "error"]
            )
            duration_ms = random.randint(100, 10000)
            total_tokens = random.randint(100, 50000)
            model_name = random.choice(["gpt-4", "claude-3", "gpt-3.5-turbo"])

            await cur.execute(
                """
                INSERT INTO swe_tracing_traces
                (trace_id, source_id, user_id, session_id, start_time, end_time,
                 duration_ms, status, total_tokens, total_input_tokens, total_output_tokens,
                 model_name, channel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    trace_id,
                    source_id,
                    user_id,
                    session_id,
                    start_time,
                    start_time + timedelta(milliseconds=duration_ms),
                    duration_ms,
                    status,
                    total_tokens,
                    total_tokens // 2,
                    total_tokens // 2,
                    model_name,
                    random.choice(channels),
                ),
            )
            inserted += 1

            if inserted % batch_size == 0:
                await conn.commit()
                print(f"    已插入 {inserted}/{to_insert} traces...")

        await conn.commit()
        print(f"  完成 traces 插入，共 {inserted} 条")

    return traces


async def insert_spans(
    conn: aiomysql.Connection,
    traces: list[dict[str, Any]],
    target: int,
) -> None:
    """插入 spans 数据，保持与 traces 的关联关系。"""
    async with conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) as cnt FROM swe_tracing_spans")
        row = await cur.fetchone()
        existing = row[0]

    if existing >= target:
        print(f"  spans 已有 {existing} 条，跳过插入")
        return

    if not traces:
        # 从数据库获取已存在的 traces
        print("  从数据库获取 traces...")
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT trace_id, user_id, session_id, source_id FROM swe_tracing_traces",
            )
            rows = await cur.fetchall()
            traces = [
                {
                    "trace_id": r[0],
                    "user_id": r[1],
                    "session_id": r[2],
                    "source_id": r[3],
                }
                for r in rows
            ]

    to_insert = target - existing
    print(f"  需要插入 {to_insert} 条 spans...")

    event_types = [
        "llm_input",
        "llm_output",
        "tool_call_start",
        "tool_call_end",
    ]
    batch_size = 2000
    inserted = 0

    async with conn.cursor() as cur:
        for i in range(to_insert):
            trace = random.choice(traces)
            span_id = generate_trace_id()

            # 80% 的 span 有 skill_name
            skill_name = None
            if random.random() < 0.8:
                skill_name = generate_skill_name(i)

            event_type = random.choice(event_types)
            start_time = trace["start_time"] + timedelta(
                seconds=random.randint(0, 10),
            )

            await cur.execute(
                """
                INSERT INTO swe_tracing_spans
                (span_id, trace_id, source_id, user_id, session_id, event_type,
                 start_time, skill_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    span_id,
                    trace["trace_id"],
                    trace["source_id"],
                    trace["user_id"],
                    trace["session_id"],
                    event_type,
                    start_time,
                    skill_name,
                ),
            )
            inserted += 1

            if inserted % batch_size == 0:
                await conn.commit()
                print(f"    已插入 {inserted}/{to_insert} spans...")

        await conn.commit()
        print(f"  完成 spans 插入，共 {inserted} 条")


async def run_original_query(conn: aiomysql.Connection) -> tuple[float, int]:
    """执行原始查询（带相关子查询）。"""
    query = """
        SELECT t.user_id,
               COUNT(DISTINCT t.session_id) as total_sessions,
               COUNT(*) as total_conversations,
               SUM(t.total_tokens) as total_tokens,
               MAX(t.start_time) as last_active,
               COUNT(CASE WHEN t.session_id NOT LIKE 'cron-task:%%' THEN 1 END) as manual_calls,
               (SELECT COUNT(*) FROM swe_tracing_spans s
                WHERE s.trace_id IN (SELECT trace_id FROM swe_tracing_traces WHERE user_id = t.user_id)
                AND s.skill_name IS NOT NULL) as total_skills
        FROM swe_tracing_traces t
        WHERE t.source_id = 'default'
          AND t.user_id != 'default'
          AND t.user_id NOT LIKE '80%%'
          AND t.user_id NOT LIKE 'IT%%'
        GROUP BY t.user_id
        ORDER BY manual_calls DESC, user_id ASC
        LIMIT 20 OFFSET 0
    """

    start = time.time()
    async with conn.cursor() as cur:
        await cur.execute(query)
        rows = await cur.fetchall()
    elapsed = time.time() - start

    return elapsed, len(rows)


async def run_optimized_query(conn: aiomysql.Connection) -> tuple[float, int]:
    """执行优化后的查询（使用 LEFT JOIN）。"""
    query = """
        SELECT t.user_id,
               COUNT(DISTINCT t.session_id) as total_sessions,
               COUNT(*) as total_conversations,
               SUM(t.total_tokens) as total_tokens,
               MAX(t.start_time) as last_active,
               COUNT(CASE WHEN t.session_id NOT LIKE 'cron-task:%%' THEN 1 END) as manual_calls,
               COALESCE(sk.skill_count, 0) as total_skills
        FROM swe_tracing_traces t
        LEFT JOIN (
            SELECT tr.user_id, COUNT(*) as skill_count
            FROM swe_tracing_spans s
            INNER JOIN swe_tracing_traces tr ON s.trace_id = tr.trace_id
            WHERE s.skill_name IS NOT NULL
              AND tr.source_id = 'default'
            GROUP BY tr.user_id
        ) sk ON sk.user_id = t.user_id
        WHERE t.source_id = 'default'
          AND t.user_id != 'default'
          AND t.user_id NOT LIKE '80%%'
          AND t.user_id NOT LIKE 'IT%%'
        GROUP BY t.user_id
        ORDER BY manual_calls DESC, user_id ASC
        LIMIT 20 OFFSET 0
    """

    start = time.time()
    async with conn.cursor() as cur:
        await cur.execute(query)
        rows = await cur.fetchall()
    elapsed = time.time() - start

    return elapsed, len(rows)


async def explain_original(conn: aiomysql.Connection) -> None:
    """分析原始查询的执行计划。"""
    query = """
        EXPLAIN
        SELECT t.user_id,
               (SELECT COUNT(*) FROM swe_tracing_spans s
                WHERE s.trace_id IN (SELECT trace_id FROM swe_tracing_traces WHERE user_id = t.user_id)
                AND s.skill_name IS NOT NULL) as total_skills
        FROM swe_tracing_traces t
        WHERE t.source_id = 'default'
          AND t.user_id != 'default'
        GROUP BY t.user_id
        LIMIT 20
    """

    print("\n原始查询执行计划:")
    async with conn.cursor() as cur:
        await cur.execute(query)
        rows = await cur.fetchall()
        for row in rows:
            print(f"  {row}")


async def explain_optimized(conn: aiomysql.Connection) -> None:
    """分析优化后查询的执行计划。"""
    query = """
        EXPLAIN
        SELECT t.user_id, COALESCE(sk.skill_count, 0) as total_skills
        FROM swe_tracing_traces t
        LEFT JOIN (
            SELECT tr.user_id, COUNT(*) as skill_count
            FROM swe_tracing_spans s
            INNER JOIN swe_tracing_traces tr ON s.trace_id = tr.trace_id
            WHERE s.skill_name IS NOT NULL
              AND tr.source_id = 'default'
            GROUP BY tr.user_id
        ) sk ON sk.user_id = t.user_id
        WHERE t.source_id = 'default'
          AND t.user_id != 'default'
        GROUP BY t.user_id
        LIMIT 20
    """

    print("\n优化后查询执行计划:")
    async with conn.cursor() as cur:
        await cur.execute(query)
        rows = await cur.fetchall()
        for row in rows:
            print(f"  {row}")


async def main():
    """主函数。"""
    print("连接数据库...")
    conn = await aiomysql.connect(**DB_CONFIG)

    try:
        # 1. 查看现有数据量
        print("\n1. 查看现有数据量:")
        counts = await get_existing_counts(conn)
        for table, count in counts.items():
            print(f"  {table}: {count} 条")

        # 2. 构造测试数据
        print("\n2. 构造测试数据:")
        traces = await insert_traces(
            conn, counts["swe_tracing_traces"], TARGET_TRACES
        )
        await insert_spans(conn, traces, TARGET_SPANS)

        # 3. 再次查看数据量
        print("\n3. 构造后的数据量:")
        counts = await get_existing_counts(conn)
        for table, count in counts.items():
            print(f"  {table}: {count} 条")

        # 4. 执行执行计划分析
        print("\n4. 执行计划分析:")
        await explain_original(conn)
        await explain_optimized(conn)

        # 5. 执行性能对比
        print("\n5. 性能对比测试:")

        print("  执行原始查询...")
        orig_time, orig_rows = await run_original_query(conn)
        print(f"    原始查询耗时: {orig_time:.3f}s, 返回 {orig_rows} 行")

        print("  执行优化查询...")
        opt_time, opt_rows = await run_optimized_query(conn)
        print(f"    优化查询耗时: {opt_time:.3f}s, 返回 {opt_rows} 行")

        print(f"\n性能提升: {orig_time / opt_time:.1f}x")

    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
