# -*- coding: utf-8 -*-
"""生成 HTML 预览点击事件测试数据（运营看板漏斗图用）.

为"任务执行概览"漏斗图第四层"点击数"提供测试数据.
关键约束:
    - swe_html_preview_click_events.cron_task_id 需要关联到已存在的定时任务
    - button_type 分布: insight, phone, other
    - clicked_at 时间需要在查询时间范围内

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_click_events_data.py
    .venv/Scripts/python.exe monitor/scripts/seed_click_events_data.py --source-id default
"""

import asyncio
import argparse
import json
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

# 按钮类型分布权重
BUTTON_TYPES = ["insight", "phone", "other"]
BUTTON_WEIGHTS = [50, 35, 15]  # insight 50%, phone 35%, other 15%

# 按钮名称映射
BUTTON_NAMES = {
    "insight": ["洞察", "洞察页面", "查看详情"],
    "phone": ["电访", "电话访问", "拨打电话"],
    "other": ["立即跟进", "发送提醒", "标记已处理"],
}


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS swe_html_preview_click_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  source_id VARCHAR(64) NULL COMMENT '来源标识',
  user_id VARCHAR(128) NULL COMMENT '点击用户标识',
  bbk_id VARCHAR(128) NULL COMMENT '分行/机构标识',
  cron_task_id VARCHAR(128) NULL COMMENT '定时任务ID',
  cron_task_name VARCHAR(255) NULL COMMENT '定时任务名称',
  file_url TEXT NOT NULL COMMENT 'HTML 文件链接',
  file_name VARCHAR(512) NULL COMMENT 'HTML 文件名',
  list_key VARCHAR(1024) NULL COMMENT '名单稳定标识',
  list_name VARCHAR(512) NULL COMMENT '名单展示名称',
  button_id VARCHAR(255) NULL COMMENT '按钮稳定标识',
  button_name VARCHAR(255) NULL COMMENT '按钮展示名称',
  button_text VARCHAR(512) NULL COMMENT '按钮文本兜底',
  button_type VARCHAR(32) NULL COMMENT '按钮类型',
  customer_id VARCHAR(128) NULL COMMENT '客户唯一标识',
  customer_name VARCHAR(255) NULL COMMENT '客户展示名称',
  customer_info JSON NULL COMMENT '客户扩展信息',
  clicked_at DATETIME NOT NULL COMMENT '前端点击时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
  INDEX idx_clicked_at (clicked_at),
  INDEX idx_task_clicked (cron_task_id, clicked_at),
  INDEX idx_button_type_clicked (button_type, clicked_at),
  INDEX idx_source_clicked (source_id, clicked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='HTML 预览按钮点击明细'
"""


async def get_existing_cron_tasks(db, source_id):
    """获取已存在的定时任务 ID 列表."""
    rows = await db.fetch_all(
        """
        SELECT DISTINCT id, tenant_id, bbk_id, name
        FROM swe_cron_jobs
        WHERE source_id = %s
          AND status != 'deleted'
          AND deleted_at IS NULL
          AND tenant_id != 'default'
          AND name LIKE 'test-cron-%%'
        """,
        (source_id,),
    )
    return [
        (row["id"], row["tenant_id"], row["bbk_id"], row["name"])
        for row in rows
    ]


async def create_click_events(db, cron_tasks, start_date, end_date, source_id):
    """生成点击事件数据."""
    if not cron_tasks:
        print("警告: 未找到已存在的定时任务，请先运行 seed_cron_test_data.py")
        return 0

    insert_count = 0
    events_batch = []

    insert_sql = """
        INSERT INTO swe_html_preview_click_events (
            source_id, user_id, bbk_id, cron_task_id, cron_task_name,
            file_url, file_name, list_key, list_name,
            button_id, button_name, button_text, button_type,
            customer_id, customer_name, customer_info, clicked_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
    """

    current_date = start_date.date()
    end_day = end_date.date()

    while current_date <= end_day:
        is_weekend = current_date.weekday() >= 5
        daily_count = (
            random.randint(20, 50) if not is_weekend else random.randint(5, 15)
        )

        day_label = current_date.strftime("%Y-%m-%d")
        day_type = "周末" if is_weekend else "工作日"
        print(f"  {day_label} ({day_type}): 计划生成 {daily_count} 条点击")

        for _ in range(daily_count):
            task_id, tenant_id, bbk_id, task_name = random.choice(cron_tasks)

            hour = random.randint(8, 20)
            clicked_at = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                hour,
                random.randint(0, 59),
                random.randint(0, 59),
            )

            button_type = random.choices(
                BUTTON_TYPES, weights=BUTTON_WEIGHTS, k=1
            )[0]
            button_name = random.choice(BUTTON_NAMES[button_type])
            button_id = f"btn-{uuid.uuid4().hex[:8]}"

            file_url = f"https://example.com/{task_id[:8]}.html"
            file_name = f"{task_name.replace('test-cron-', '')}.html"

            customer_id = f"CUST-{random.randint(10000, 99999)}"
            customer_name = random.choice(
                ["张三", "李四", "王五", "赵六", "钱七", "祝话", "程广泛"]
            )

            customer_info = {
                "客户姓名": customer_name,
                "客户编号": customer_id,
            }

            events_batch.append(
                (
                    source_id,
                    f"user-{random.randint(10000, 99999)}",
                    bbk_id,
                    task_id,
                    task_name,
                    file_url,
                    file_name,
                    file_url,
                    file_name,
                    button_id,
                    button_name,
                    button_name,
                    button_type,
                    customer_id,
                    customer_name,
                    json.dumps(customer_info),
                    clicked_at,
                ),
            )

            insert_count += 1

            if len(events_batch) >= 200:
                await db.execute_many(insert_sql, events_batch)
                events_batch = []

        current_date += timedelta(days=1)

    if events_batch:
        await db.execute_many(insert_sql, events_batch)

    return insert_count


async def verify_results(db, source_id, start_date, end_date):
    """验证插入结果."""
    print("\n=== 点击按钮类型分布 ===")
    rows = await db.fetch_all(
        """
        SELECT button_type, COUNT(*) as cnt
        FROM swe_html_preview_click_events
        WHERE source_id <=> %s
          AND clicked_at >= %s AND clicked_at <= %s
        GROUP BY button_type ORDER BY cnt DESC
        """,
        (source_id, start_date, end_date),
    )
    for row in rows:
        print(f"  {row['button_type']}: {row['cnt']} 次")

    print("\n=== 按定时任务统计点击数 ===")
    rows = await db.fetch_all(
        """
        SELECT cron_task_id, COUNT(*) as click_count
        FROM swe_html_preview_click_events
        WHERE source_id <=> %s
          AND clicked_at >= %s AND clicked_at <= %s
        GROUP BY cron_task_id ORDER BY click_count DESC
        LIMIT 10
        """,
        (source_id, start_date, end_date),
    )
    for row in rows:
        print(f"  {row['cron_task_id'][:20]}: {row['click_count']} 次")

    # 验证运营看板漏斗图第四层查询
    print("\n=== 运营看板漏斗图第四层统计 ===")
    result = await db.fetch_one(
        """
        SELECT
            COUNT(*) as total_clicks,
            COUNT(DISTINCT cron_task_id) as unique_tasks
        FROM swe_html_preview_click_events
        WHERE source_id <=> %s
          AND clicked_at >= %s AND clicked_at <= %s
        """,
        (source_id, start_date, end_date),
    )
    print(
        f"  总点击数: {result['total_clicks']}, 唯一任务数: {result['unique_tasks']}"
    )

    # 验证 button_type 分布统计
    print("\n=== button_type 分布统计 ===")
    rows = await db.fetch_all(
        """
        SELECT button_type, COUNT(*) as cnt
        FROM swe_html_preview_click_events
        WHERE source_id <=> %s
          AND clicked_at >= %s AND clicked_at <= %s
        GROUP BY button_type
        """,
        (source_id, start_date, end_date),
    )
    button_type_dict = {row["button_type"]: row["cnt"] for row in rows}
    print(f"  分布: {button_type_dict}")


async def main():
    """生成近30天 HTML 预览点击事件测试数据."""
    parser = argparse.ArgumentParser(
        description="生成 HTML 预览点击事件测试数据"
    )
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
        # 创建表（如果不存在）
        await db.execute(CREATE_TABLE_SQL)
        print("表 swe_html_preview_click_events 已就绪\n")

        # 清理旧测试数据
        await db.execute(
            "DELETE FROM swe_html_preview_click_events WHERE cron_task_id LIKE 'test-cron-%'",
        )
        print("已清理旧点击事件数据\n")

        # 获取已存在的定时任务
        cron_tasks = await get_existing_cron_tasks(db, source_id)
        print(f"找到 {len(cron_tasks)} 个已存在的定时任务")

        if not cron_tasks:
            print("\n请先运行 seed_cron_test_data.py 生成定时任务数据")
            return

        start_date = datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) - timedelta(days=29)
        end_date = datetime.now()

        insert_count = await create_click_events(
            db,
            cron_tasks,
            start_date,
            end_date,
            source_id,
        )

        print(f"\n共插入 {insert_count} 条点击事件记录")
        print(
            f"时间范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
        )

        await verify_results(db, source_id, start_date, end_date)

    except Exception as e:
        print(f"插入失败: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
