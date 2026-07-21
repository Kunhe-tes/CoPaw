# -*- coding: utf-8 -*-
"""快速构造大规模测试数据。

目标：模拟线上数据量
- swe_tracing_traces: ~70000 条
- swe_tracing_spans: ~1400000 条（约 20 倍于 traces）
"""

import asyncio
import random
import string
import time
from datetime import datetime, timedelta

import aiomysql

DB_CONFIG = {
    "host": "120.48.112.239",
    "port": 3306,
    "user": "mysqladmin",
    "password": "123456",
    "db": "rmassistdata",
    "charset": "utf8mb4",
    "autocommit": False,
}

NUM_USERS = 2000  # 增加用户数量
TARGET_TRACES = 70000
TARGET_SPANS = 1400000


def gen_uuid() -> str:
    return "".join(random.choices(string.hexdigits.lower(), k=32))


async def fast_insert():
    print("连接数据库...")
    pool = await aiomysql.create_pool(
        **DB_CONFIG,
        minsize=1,
        maxsize=5,
    )

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM swe_tracing_traces")
            existing_traces = (await cur.fetchone())[0]
            await cur.execute("SELECT COUNT(*) FROM swe_tracing_spans")
            existing_spans = (await cur.fetchone())[0]

    print(f"现有数据: traces={existing_traces}, spans={existing_spans}")

    # 生成用户 ID 池
    users = []
    for i in range(NUM_USERS):
        prefix = random.choice(["", "80", "IT", "agent_"])
        users.append(f"{prefix}user_{i:05d}")

    sources = ["default", "prod", "test", "dev"]
    channels = ["console", "webhook", "api"]
    models = ["gpt-4", "claude-3", "gpt-3.5-turbo"]
    statuses = ["completed", "completed", "completed", "error", "cancelled"]
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

    base_time = datetime.now() - timedelta(days=30)

    # 1. 批量插入 traces
    traces_to_insert = max(0, TARGET_TRACES - existing_traces)
    if traces_to_insert > 0:
        print(f"\n插入 {traces_to_insert} 条 traces...")
        batch_size = 5000
        traces_data = []

        start = time.time()
        for i in range(traces_to_insert):
            trace_id = gen_uuid()
            user_id = random.choice(users)
            session_id = gen_uuid()
            source_id = random.choice(sources)
            start_time = base_time + timedelta(
                seconds=random.randint(0, 30 * 24 * 3600)
            )
            duration_ms = random.randint(100, 30000)
            total_tokens = random.randint(100, 50000)

            traces_data.append(
                (
                    trace_id,
                    source_id,
                    user_id,
                    session_id,
                    start_time,
                    start_time + timedelta(milliseconds=duration_ms),
                    duration_ms,
                    random.choice(statuses),
                    total_tokens,
                    total_tokens // 2,
                    total_tokens // 2,
                    random.choice(models),
                    random.choice(channels),
                )
            )

            if len(traces_data) >= batch_size:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.executemany(
                            """
                            INSERT INTO swe_tracing_traces
                            (trace_id, source_id, user_id, session_id, start_time, end_time,
                             duration_ms, status, total_tokens, total_input_tokens, total_output_tokens,
                             model_name, channel)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            traces_data,
                        )
                        await conn.commit()
                traces_data = []
                elapsed = time.time() - start
                print(
                    f"  已插入 {i + 1}/{traces_to_insert} traces, 耗时 {elapsed:.1f}s"
                )

        # 插入剩余数据
        if traces_data:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(
                        """
                        INSERT INTO swe_tracing_traces
                        (trace_id, source_id, user_id, session_id, start_time, end_time,
                         duration_ms, status, total_tokens, total_input_tokens, total_output_tokens,
                         model_name, channel)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        traces_data,
                    )
                    await conn.commit()

        print(f"完成 traces 插入，总耗时 {time.time() - start:.1f}s")

    # 获取所有 trace_id 用于插入 spans
    print("\n加载 trace_id 列表...")
    all_traces = []
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT trace_id, source_id, user_id, session_id, start_time FROM swe_tracing_traces"
            )
            all_traces = await cur.fetchall()

    print(f"加载了 {len(all_traces)} 条 traces")

    # 2. 批量插入 spans（约 20 倍于 traces）
    spans_to_insert = max(0, TARGET_SPANS - existing_spans)
    if spans_to_insert > 0:
        print(f"\n插入 {spans_to_insert} 条 spans...")
        batch_size = 10000
        spans_data = []

        start = time.time()
        for i in range(spans_to_insert):
            trace = random.choice(all_traces)
            span_id = gen_uuid()
            event_type = random.choice(
                ["llm_input", "llm_output", "tool_call_start", "tool_call_end"]
            )
            skill_name = (
                random.choice(skills) if random.random() < 0.8 else None
            )

            spans_data.append(
                (
                    span_id,
                    trace[0],  # trace_id
                    trace[1],  # source_id
                    trace[2],  # user_id
                    trace[3],  # session_id
                    event_type,
                    trace[4] + timedelta(seconds=random.randint(0, 10)),
                    skill_name,
                )
            )

            if len(spans_data) >= batch_size:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.executemany(
                            """
                            INSERT INTO swe_tracing_spans
                            (span_id, trace_id, source_id, user_id, session_id, event_type, start_time, skill_name)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            spans_data,
                        )
                        await conn.commit()
                spans_data = []
                elapsed = time.time() - start
                print(
                    f"  已插入 {i + 1}/{spans_to_insert} spans, 耗时 {elapsed:.1f}s"
                )

        # 插入剩余数据
        if spans_data:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(
                        """
                        INSERT INTO swe_tracing_spans
                        (span_id, trace_id, source_id, user_id, session_id, event_type, start_time, skill_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        spans_data,
                    )
                    await conn.commit()

        print(f"完成 spans 插入，总耗时 {time.time() - start:.1f}s")

    # 最终统计
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM swe_tracing_traces")
            final_traces = (await cur.fetchone())[0]
            await cur.execute("SELECT COUNT(*) FROM swe_tracing_spans")
            final_spans = (await cur.fetchone())[0]

    print(f"\n最终数据量: traces={final_traces}, spans={final_spans}")

    pool.close()
    await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(fast_insert())
