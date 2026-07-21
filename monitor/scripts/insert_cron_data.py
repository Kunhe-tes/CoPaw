# -*- coding: utf-8 -*-
"""补充构造 cron 表数据，确保与 traces 表关联关系正确。

关联关系：
1. swe_cron_jobs.tenant_id = swe_tracing_traces.user_id
2. swe_cron_executions.job_id = swe_cron_jobs.id
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

TARGET_CRON_JOBS = 6000
TARGET_CRON_EXECUTIONS = 40000


def gen_uuid() -> str:
    return "".join(random.choices(string.hexdigits.lower(), k=32))


async def insert_cron_data():
    print("连接数据库...")
    pool = await aiomysql.create_pool(**DB_CONFIG, minsize=1, maxsize=5)

    # 获取现有数据量
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM swe_cron_jobs")
            existing_jobs = (await cur.fetchone())[0]
            await cur.execute("SELECT COUNT(*) FROM swe_cron_executions")
            existing_execs = (await cur.fetchone())[0]
            # 获取已有的 user_id 列表（从 traces 表）
            await cur.execute(
                "SELECT DISTINCT user_id FROM swe_tracing_traces"
            )
            user_ids = [r[0] for r in await cur.fetchall()]

    print(f"现有: cron_jobs={existing_jobs}, cron_executions={existing_execs}")
    print(f"从 traces 表获取了 {len(user_ids)} 个 user_id")

    sources = ["default", "prod", "test", "dev"]
    channels = ["console", "webhook", "api"]
    task_types = ["text", "agent"]
    statuses = ["active", "active", "active", "paused"]
    exec_statuses = ["success", "success", "success", "error", "timeout"]

    base_time = datetime.now() - timedelta(days=30)

    # 1. 插入 cron_jobs
    jobs_to_insert = max(0, TARGET_CRON_JOBS - existing_jobs)
    if jobs_to_insert > 0:
        print(f"\n插入 {jobs_to_insert} 条 cron_jobs...")
        batch_size = 1000
        jobs_data = []
        job_ids = []

        start = time.time()
        for i in range(jobs_to_insert):
            job_id = gen_uuid()
            tenant_id = random.choice(user_ids)  # 关联到 traces 的 user_id
            source_id = random.choice(sources)

            jobs_data.append(
                (
                    job_id,
                    f"任务_{i:05d}",
                    tenant_id,
                    f"用户_{random.randint(1, 500)}",
                    f"BBK_{random.randint(1, 100)}",
                    source_id,
                    random.choice(task_types),
                    "0 */5 * * *",  # cron 表达式
                    random.choice(channels),
                    random.choice(statuses),
                )
            )
            job_ids.append(job_id)

            if len(jobs_data) >= batch_size:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.executemany(
                            """
                            INSERT INTO swe_cron_jobs
                            (id, name, tenant_id, tenant_name, bbk_id, source_id,
                             task_type, cron_expr, channel, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            jobs_data,
                        )
                        await conn.commit()
                jobs_data = []
                print(f"  已插入 {i + 1}/{jobs_to_insert} jobs...")

        if jobs_data:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(
                        """
                        INSERT INTO swe_cron_jobs
                        (id, name, tenant_id, tenant_name, bbk_id, source_id,
                         task_type, cron_expr, channel, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        jobs_data,
                    )
                    await conn.commit()

        print(f"完成 cron_jobs 插入，耗时 {time.time() - start:.1f}s")

    # 获取所有 job_id
    print("\n加载 job_id 列表...")
    all_job_ids = []
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, tenant_id, source_id FROM swe_cron_jobs"
            )
            all_job_ids = await cur.fetchall()

    print(f"加载了 {len(all_job_ids)} 个 jobs")

    # 2. 插入 cron_executions
    execs_to_insert = max(0, TARGET_CRON_EXECUTIONS - existing_execs)
    if execs_to_insert > 0:
        print(f"\n插入 {execs_to_insert} 条 cron_executions...")
        batch_size = 2000
        execs_data = []

        start = time.time()
        for i in range(execs_to_insert):
            job = random.choice(all_job_ids)
            exec_status = random.choice(exec_statuses)
            actual_time = base_time + timedelta(
                seconds=random.randint(0, 30 * 24 * 3600)
            )

            execs_data.append(
                (
                    job[0],  # job_id
                    f"任务_{random.randint(1, 1000)}",
                    job[1],  # tenant_id
                    actual_time,
                    actual_time + timedelta(seconds=random.randint(1, 300)),
                    random.randint(100, 300000),  # duration_ms
                    exec_status,
                    random.random() < 0.3,  # is_read
                )
            )

            if len(execs_data) >= batch_size:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.executemany(
                            """
                            INSERT INTO swe_cron_executions
                            (job_id, job_name, tenant_id, actual_time, end_time,
                             duration_ms, status, is_read)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            execs_data,
                        )
                        await conn.commit()
                execs_data = []
                print(f"  已插入 {i + 1}/{execs_to_insert} executions...")

        if execs_data:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(
                        """
                        INSERT INTO swe_cron_executions
                        (job_id, job_name, tenant_id, actual_time, end_time,
                         duration_ms, status, is_read)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        execs_data,
                    )
                    await conn.commit()

        print(f"完成 cron_executions 插入，耗时 {time.time() - start:.1f}s")

    # 最终统计
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM swe_tracing_traces")
            traces = (await cur.fetchone())[0]
            await cur.execute("SELECT COUNT(*) FROM swe_tracing_spans")
            spans = (await cur.fetchone())[0]
            await cur.execute("SELECT COUNT(*) FROM swe_cron_jobs")
            jobs = (await cur.fetchone())[0]
            await cur.execute("SELECT COUNT(*) FROM swe_cron_executions")
            execs = (await cur.fetchone())[0]

    print("\n最终数据量:")
    print(f"  swe_tracing_traces: {traces} (目标: 68703)")
    print(f"  swe_tracing_spans: {spans} (目标: 1378752)")
    print(f"  swe_cron_jobs: {jobs} (目标: 5756)")
    print(f"  swe_cron_executions: {execs} (目标: 39146)")

    pool.close()
    await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(insert_cron_data())
