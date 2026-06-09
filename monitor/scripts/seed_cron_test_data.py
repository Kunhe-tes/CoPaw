# -*- coding: utf-8 -*-
"""生成近30天定时任务执行测试数据（运营看板漏斗图用）.

为"任务执行概览"漏斗图提供测试数据.
关键约束:
    - cron_jobs.source_id 可通过命令行参数指定（默认 UPPCLAW）
    - cron_jobs.tenant_id 不能为 "default"（否则被查询过滤掉）
    - cron_jobs.status 不能为 "deleted"
    - cron_jobs.deleted_at IS NULL
    - cron_executions.is_read 用于漏斗图的已读统计

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_cron_test_data.py
    .venv/Scripts/python.exe monitor/scripts/seed_cron_test_data.py --source-id default
"""

import asyncio
import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# 添加 swe src 目录到 Python 路径
swe_src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(swe_src_path))

from swe.envs import load_envs_into_environ

load_envs_into_environ()

from swe.database import get_database_config, DatabaseConnection

# 默认 source_id
DEFAULT_SOURCE_ID = "UPPCLAW"

BBK_IDS = ["100", "200", "201", "202", "203", "204", "205", "206", "V00"]
CRON_JOB_NAMES = [
    "日报数据汇总",
    "客户画像更新",
    "风险监控扫描",
    "营销报表生成",
    "数据质量检查",
    "系统日志归档",
    "业务指标推送",
    "合规审查任务",
    "客户回访提醒",
    "库存预警通知",
]

# 执行状态分布权重
STATUS_WEIGHTS = [
    85,
    8,
    3,
    2,
    2,
]  # success, error, timeout, cancelled, skipped
STATUSES = ["success", "error", "timeout", "cancelled", "skipped"]


async def create_test_jobs(db, bbk_ids, job_names):
    """创建测试定时任务."""
    job_ids = []
    for bbk_id in bbk_ids:
        for i in range(random.randint(6, 12)):
            job_id = f"test-cron-{uuid.uuid4().hex[:12]}"
            job_name = f"test-cron-{random.choice(job_names)}"
            task_type = random.choice(["text", "agent"])

            await db.execute(
                """
                INSERT INTO swe_cron_jobs (
                    id, name, tenant_id, tenant_name, bbk_id, source_id,
                    enabled, task_type, cron_expr, timezone, channel,
                    target_user_id, timeout_seconds, status, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    job_id,
                    job_name,
                    f"tenant-{bbk_id}",
                    f"租户{bbk_id}",
                    bbk_id,
                    "default",
                    True,
                    task_type,
                    "0 9 * * *",
                    "Asia/Shanghai",
                    "web",
                    f"user-{random.randint(10000, 99999)}",
                    7200,
                    "active",
                    datetime.now(),
                ),
            )
            job_ids.append(job_id)
    return job_ids


async def create_executions(db, job_ids, start_date, end_date):
    """为测试任务生成执行记录."""
    exec_count = 0
    current_date = start_date.date()
    end_day = end_date.date()

    while current_date <= end_day:
        is_weekend = current_date.weekday() >= 5
        daily_execs = (
            random.randint(40, 80)
            if not is_weekend
            else random.randint(10, 30)
        )

        for _ in range(daily_execs):
            job_id = random.choice(job_ids)
            status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
            exec_time = datetime.combine(
                current_date,
                datetime.min.time(),
            ) + timedelta(
                hours=random.randint(8, 18),
                minutes=random.randint(0, 59),
            )
            duration = (
                random.randint(100, 30000)
                if status != "timeout"
                else random.randint(30000, 120000)
            )

            exec_id = f"test-exec-{uuid.uuid4().hex[:12]}"
            await db.execute(
                """
                INSERT INTO swe_cron_executions (
                    id, job_id, status, started_at, finished_at,
                    duration_ms, error_message, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    exec_id,
                    job_id,
                    status,
                    exec_time,
                    exec_time + timedelta(milliseconds=duration),
                    duration,
                    "测试错误信息" if status == "error" else None,
                    exec_time,
                ),
            )
            exec_count += 1

        current_date += timedelta(days=1)

    return exec_count


async def create_jobs_and_generate_executions(
    db, start_date, end_date, source_id
):
    """创建测试任务并生成执行记录."""
    # 每个分行创建多个测试任务
    job_ids = []
    for bbk_id in BBK_IDS:
        for _ in range(random.randint(6, 12)):
            job_id = f"test-cron-{uuid.uuid4().hex[:12]}"
            job_name = f"test-cron-{random.choice(CRON_JOB_NAMES)}"
            task_type = random.choice(["text", "agent"])

            await db.execute(
                """
                INSERT INTO swe_cron_jobs (
                    id, name, tenant_id, tenant_name, bbk_id, source_id,
                    enabled, task_type, cron_expr, timezone, channel,
                    target_user_id, timeout_seconds, status, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    job_id,
                    job_name,
                    f"tenant-{bbk_id}",
                    f"租户{bbk_id}",
                    bbk_id,
                    source_id,
                    True,
                    task_type,
                    "0 9 * * *",
                    "Asia/Shanghai",
                    "web",
                    f"user-{random.randint(10000, 99999)}",
                    7200,
                    "active",
                    datetime.now(),
                ),
            )
            job_ids.append((job_id, bbk_id))

    print(f"创建了 {len(job_ids)} 个测试定时任务\n")

    insert_count = 0
    executions_batch = []

    insert_sql = """
        INSERT INTO swe_cron_executions (
            job_id, job_name, tenant_id, scheduled_time, actual_time,
            end_time, duration_ms, status, error_message, instance_id,
            trace_id, session_id, is_read, read_at, created_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
    """

    current_date = start_date.date()
    end_day = end_date.date()

    while current_date <= end_day:
        is_weekend = current_date.weekday() >= 5
        daily_count = (
            random.randint(60, 120)
            if not is_weekend
            else random.randint(20, 50)
        )

        day_label = current_date.strftime("%Y-%m-%d")
        day_type = "周末" if is_weekend else "工作日"
        print(f"  {day_label} ({day_type}): 计划生成 {daily_count} 条")

        for _ in range(daily_count):
            job_id, bbk_id = random.choice(job_ids)

            hour = random.randint(6, 22)
            actual_time = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                hour,
                random.randint(0, 59),
                random.randint(0, 59),
            )
            scheduled_time = actual_time - timedelta(
                minutes=random.randint(0, 5),
            )

            duration_ms = random.randint(1000, 60000)
            end_time = actual_time + timedelta(milliseconds=duration_ms)

            status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

            # 已读状态：成功的任务约70%已读，失败的任务约20%已读
            is_read_prob = 0.7 if status == "success" else 0.2
            is_read = 1 if random.random() < is_read_prob else 0
            read_at = end_time if is_read else None

            error_message = (
                "模拟错误" if status in ("error", "timeout") else ""
            )

            executions_batch.append(
                (
                    job_id,
                    f"test-cron-{job_id[:6]}",
                    f"tenant-{bbk_id}",
                    scheduled_time,
                    actual_time,
                    end_time,
                    duration_ms,
                    status,
                    error_message,
                    uuid.uuid4().hex[:12],
                    uuid.uuid4().hex[:24],
                    uuid.uuid4().hex[:16],
                    is_read,
                    read_at,
                    actual_time,
                ),
            )

            insert_count += 1

            if len(executions_batch) >= 200:
                await db.execute_many(insert_sql, executions_batch)
                executions_batch = []

        current_date += timedelta(days=1)

    if executions_batch:
        await db.execute_many(insert_sql, executions_batch)

    return insert_count


async def verify_results(db, start_date, end_date, source_id):
    """验证插入结果."""
    print("\n=== 执行状态分布 ===")
    rows = await db.fetch_all("""
        SELECT e.status, COUNT(*) as cnt
        FROM swe_cron_executions e
        INNER JOIN swe_cron_jobs j ON e.job_id = j.id
        WHERE j.name LIKE 'test-cron-%'
        GROUP BY e.status ORDER BY cnt DESC
    """)
    for row in rows:
        print(f"  {row['status']}: {row['cnt']} 次")

    print("\n=== 已读分布 ===")
    read_result = await db.fetch_all("""
        SELECT e.is_read, COUNT(*) as cnt
        FROM swe_cron_executions e
        INNER JOIN swe_cron_jobs j ON e.job_id = j.id
        WHERE j.name LIKE 'test-cron-%'
        GROUP BY e.is_read
    """)
    for row in read_result:
        label = "已读" if row["is_read"] else "未读"
        print(f"  {label}: {row['cnt']} 次")

    # 验证运营看板查询条件
    print("\n=== 匹配运营看板漏斗图查询条件 ===")
    result = await db.fetch_one(
        """
        SELECT
            COUNT(*) as total_tasks,
            SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN e.is_read = 1 THEN 1 ELSE 0 END) as read_count
        FROM swe_cron_executions e
        INNER JOIN swe_cron_jobs j ON e.job_id = j.id
        WHERE e.actual_time >= %s AND e.actual_time <= %s
          AND j.status != 'deleted'
          AND j.deleted_at IS NULL
          AND j.source_id = %s
          AND j.tenant_id != 'default'
    """,
        (start_date, end_date, source_id),
    )
    print(
        f"  总任务: {result['total_tasks']}, "
        f"成功: {result['success']}, "
        f"已读: {result['read_count']}",
    )


async def main():
    """生成近30天定时任务执行测试数据."""
    parser = argparse.ArgumentParser(description="生成定时任务测试数据")
    parser.add_argument(
        "--source-id",
        default=DEFAULT_SOURCE_ID,
        help=f"数据来源标识（默认: {DEFAULT_SOURCE_ID})",
    )
    args = parser.parse_args()
    source_id = args.source_id

    db_config = get_database_config()
    print(f"数据库: {db_config.host}:{db_config.port}/{db_config.database}")
    print(f"source_id: {source_id}")

    db = DatabaseConnection(db_config)
    await db.connect()
    print("数据库连接成功\n")

    try:
        # 清理旧测试数据
        job_ids_result = await db.fetch_all(
            "SELECT id FROM swe_cron_jobs WHERE name LIKE 'test-cron-%'",
        )
        test_job_ids = [row["id"] for row in job_ids_result]
        if test_job_ids:
            placeholders = ", ".join(["%s"] * len(test_job_ids))
            await db.execute(
                f"DELETE FROM swe_cron_executions WHERE job_id IN ({placeholders})",  # noqa: E501
                tuple(test_job_ids),
            )
            await db.execute(
                f"DELETE FROM swe_cron_jobs WHERE id IN ({placeholders})",
                tuple(test_job_ids),
            )
            print(f"已清理 {len(test_job_ids)} 个旧测试任务及执行记录\n")

        start_date = datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) - timedelta(days=29)
        end_date = datetime.now()

        insert_count = await create_jobs_and_generate_executions(
            db,
            start_date,
            end_date,
            source_id,
        )

        print(f"\n共插入 {insert_count} 条执行记录")
        print(
            f"时间范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
        )

        await verify_results(db, start_date, end_date, source_id)

    except Exception as e:
        print(f"插入失败: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
