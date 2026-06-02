# -*- coding: utf-8 -*-
"""生成近30天技能调用测试数据（运营看板用）.

为"技能使用排行榜"提供丰富的多技能测试数据.
关键约束:
    - span.source_id 必须为 "default"（匹配 x-source-id: default 请求头）
    - span.user_id 不能为 "default"（否则被查询过滤掉）

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_skill_ranking_data.py
"""

import asyncio
import json
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swe.envs import load_envs_into_environ

load_envs_into_environ()

from swe.database import get_database_config, DatabaseConnection

SKILLS = [
    ("数据分析", "对数据进行统计分析、可视化和洞察提取"),
    ("报表生成", "自动生成各类业务报表和可视化图表"),
    ("客户分析", "分析客户数据，识别客户特征和行为模式"),
    ("风险评估", "对业务或客户进行风险分析和评估"),
    ("智能问答", "基于知识库的智能问答系统，支持多轮交互"),
    ("文档处理", "处理各类文档格式转换和编辑"),
    ("邮件生成", "自动生成邮件内容和模板"),
    ("数据查询", "从数据库或数据源中查询和提取数据"),
    ("数据导出", "导出系统数据到外部文件或指定格式"),
    ("图表绘制", "生成各类统计图表和可视化图形"),
    ("客户画像", "构建客户画像，分析客户特征和偏好"),
    ("营销推荐", "基于客户数据生成个性化营销推荐方案"),
    ("合规检查", "业务合规性检查和审核"),
    ("流程自动化", "自动化业务流程处理，减少人工操作"),
    ("智能客服", "基于知识库的智能问答和客服服务"),
    ("股票分析", "分析股票市场数据和投资建议"),
    ("财务分析", "财务数据分析和报表生成"),
    ("贷款预审", "对贷款申请进行预审和风险评估"),
    ("预警通知", "发送业务预警和通知消息"),
    ("产品推荐", "基于客户需求的产品推荐"),
]

SKILL_WEIGHTS = [
    12,
    12,
    12,
    12,
    12,
    6,
    6,
    6,
    6,
    6,
    3,
    3,
    3,
    3,
    3,
    1,
    1,
    1,
    1,
    1,
]
BBK_IDS = ["100", "200", "201", "202", "203", "204", "205", "206"]


async def generate_daily_spans(  # noqa: C901
    db,
    traces,
    insert_sql,
    start_date,
    end_date,
):
    """生成每日技能调用 span 数据."""
    insert_count = 0
    spans_batch = []
    current_date = start_date.date()
    end_day = end_date.date()

    while current_date <= end_day:
        is_weekend = current_date.weekday() >= 5
        daily_spans = (
            random.randint(80, 150)
            if not is_weekend
            else random.randint(30, 60)
        )

        day_label = current_date.strftime("%Y-%m-%d")
        day_type = "周末" if is_weekend else "工作日"
        print(f"  {day_label} ({day_type}): 计划生成 {daily_spans} 条")

        for _ in range(daily_spans):
            skill_name, skill_desc = random.choices(
                SKILLS,
                weights=SKILL_WEIGHTS,
                k=1,
            )[0]

            hour = random.choices(
                [random.randint(9, 18), random.randint(0, 23)],
                weights=[70, 30],
                k=1,
            )[0]
            start_time = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                hour,
                random.randint(0, 59),
                random.randint(0, 59),
            )

            duration_ms = random.randint(500, 15000)
            span_id = f"test-skill-{uuid.uuid4().hex[:12]}"

            trace_id = span_id
            session_id = f"test-session-{uuid.uuid4().hex[:8]}"
            user_id = f"user-{random.randint(10000, 99999)}"
            bbk_id = random.choice(BBK_IDS)

            if traces:
                matching = [
                    t for t in traces if t["start_time"].date() == current_date
                ]
                if matching:
                    trace = random.choice(matching)
                    trace_id = trace["trace_id"]
                    session_id = (
                        trace["session_id"]
                        if trace["session_id"]
                        else session_id
                    )
                    user_id = trace["user_id"]
                    bbk_id = trace["bbk_id"] if trace["bbk_id"] else bbk_id

            # source_id="default" 是关键：匹配运营看板 x-source-id: default
            spans_batch.append(
                (
                    span_id,
                    trace_id,
                    "default",
                    f"skill_{skill_name}",
                    "skill_invocation",
                    start_time,
                    start_time + timedelta(milliseconds=duration_ms),
                    duration_ms,
                    user_id,
                    bbk_id,
                    session_id,
                    "web",
                    skill_name,
                    skill_desc,
                ),
            )

            insert_count += 1

            if len(spans_batch) >= 200:
                await db.execute_many(insert_sql, spans_batch)
                spans_batch = []

        current_date += timedelta(days=1)

    if spans_batch:
        await db.execute_many(insert_sql, spans_batch)

    return insert_count


async def verify_results(db, start_date, end_date):
    """验证插入结果."""
    print("\n=== 技能分布 ===")
    rows = await db.fetch_all("""
        SELECT skill_name, COUNT(*) as cnt
        FROM swe_tracing_spans
        WHERE span_id LIKE 'test-skill-%'
        GROUP BY skill_name ORDER BY cnt DESC
    """)
    for row in rows:
        print(f"  {row['skill_name']}: {row['cnt']} 次")

    total_row = await db.fetch_one(
        "SELECT COUNT(*) as cnt FROM swe_tracing_spans WHERE span_id LIKE 'test-skill-%'",
    )
    print(f"\n总计: {total_row['cnt']} 条")

    # 验证运营看板查询条件
    print("\n=== 匹配运营看板查询条件 ===")
    rows = await db.fetch_all(
        """
        SELECT skill_name, MAX(skill_description) as skill_description,
               COUNT(*) as cnt
        FROM swe_tracing_spans
        WHERE start_time >= %s AND start_time <= %s
          AND event_type = 'skill_invocation'
          AND skill_name IS NOT NULL
          AND source_id = 'default'
          AND user_id != 'default'
        GROUP BY skill_name ORDER BY cnt DESC LIMIT 10
    """,
        (start_date, end_date),
    )
    print("匹配 x-source-id=default, user_id!=default:")
    for row in rows:
        print(f"  {row['skill_name']}: {row['cnt']} 次")


async def main():
    """生成近30天技能调用测试数据."""
    db_config = get_database_config()
    print(f"数据库: {db_config.host}:{db_config.port}/{db_config.database}")

    db = DatabaseConnection(db_config)
    await db.connect()
    print("数据库连接成功\n")

    try:
        # 清理旧测试数据
        await db.execute(
            "DELETE FROM swe_tracing_spans WHERE span_id LIKE 'test-skill-%'",
        )
        print("已清理旧测试数据\n")

        start_date = datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) - timedelta(days=29)
        end_date = datetime.now()

        # 获取可关联的 trace (user_id != 'default')
        trace_query = """
            SELECT trace_id, user_id, session_id, bbk_id, start_time
            FROM swe_tracing_traces
            WHERE start_time >= %s AND start_time <= %s
              AND user_id != 'default'
            LIMIT 5000
        """
        traces = await db.fetch_all(trace_query, (start_date, end_date))

        if not traces:
            print("未找到可关联的 trace 数据，将直接生成独立 span 数据\n")
            traces = None
        else:
            print(f"找到 {len(traces)} 条 trace 可用于关联\n")

        insert_sql = """
            INSERT INTO swe_tracing_spans (
                span_id, trace_id, source_id, name, event_type,
                start_time, end_time, duration_ms, user_id,
                bbk_id, session_id, channel, skill_name, skill_description
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
        """

        insert_count = await generate_daily_spans(
            db,
            traces,
            insert_sql,
            start_date,
            end_date,
        )

        print(f"\n共插入 {insert_count} 条技能调用测试数据")
        print(
            f"时间范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
        )

        await verify_results(db, start_date, end_date)

    except Exception as e:
        print(f"插入失败: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
