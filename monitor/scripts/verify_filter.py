# -*- coding: utf-8 -*-
"""模拟排行榜 SQL,验证 UPPCLAW trace 为什么被过滤."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from monitor.app.database import DatabaseConnection, get_database_config

TRACE_ID = "6c2c6c51-bb9c-4a14-9833-cea6e5720df6"


async def main() -> None:
    db = DatabaseConnection(get_database_config())
    await db.connect()
    try:
        print("=== 该 trace 的 span 基础信息 ===\n")
        rows = await db.fetch_all(
            """
            SELECT source_id, bbk_id, user_id, skill_name, skill_id
            FROM swe_tracing_spans
            WHERE trace_id = %s AND skill_name IS NOT NULL
            """,
            (TRACE_ID,),
        )
        for r in rows:
            print(f"  {dict(r)}")
        print(f"\n共 {len(rows)} 条带 skill_name 的 span\n")

        # 1) 模拟 source_id = RMASSIST
        total_rmassist = await db.fetch_one(
            """
            SELECT COUNT(*) AS n
            FROM swe_tracing_spans
            WHERE trace_id = %s
              AND source_id = 'RMASSIST'
              AND bbk_id IS NOT NULL AND bbk_id != ''
              AND user_id != 'default'
            """,
            (TRACE_ID,),
        )
        print(f"[source=RMASSIST + bbk_id 非空] 命中 {total_rmassist['n']} 条")

        # 2) 模拟 source_id = all
        total_all = await db.fetch_one(
            """
            SELECT COUNT(*) AS n
            FROM swe_tracing_spans
            WHERE trace_id = %s
              AND source_id NOT IN ('default')
              AND bbk_id IS NOT NULL AND bbk_id != ''
              AND user_id != 'default'
            """,
            (TRACE_ID,),
        )
        print(f"[source=all + bbk_id 非空] 命中 {total_all['n']} 条")

        # 3) 仅 source_id = all, 不带 bbk_id 过滤
        total_all_no_bbk = await db.fetch_one(
            """
            SELECT COUNT(*) AS n
            FROM swe_tracing_spans
            WHERE trace_id = %s
              AND source_id NOT IN ('default')
              AND user_id != 'default'
            """,
            (TRACE_ID,),
        )
        print(
            f"[source=all, 不带 bbk_id 过滤] 命中 {total_all_no_bbk['n']} 条",
        )

        # 4) 仅 source_id = all, 不带 bbk_id 不带 user_id 过滤
        total_all_min = await db.fetch_one(
            """
            SELECT COUNT(*) AS n
            FROM swe_tracing_spans
            WHERE trace_id = %s
              AND source_id NOT IN ('default')
            """,
            (TRACE_ID,),
        )
        print(f"[source=all, 只排除 default] 命中 {total_all_min['n']} 条")

        # 5) 该 trace 涉及的 skill 在所有源/所有 bbk 的总调用次数
        skill_total = await db.fetch_one(
            """
            SELECT skill_name, COUNT(*) AS n
            FROM swe_tracing_spans
            WHERE trace_id = %s AND skill_name IS NOT NULL
            GROUP BY skill_name
            """,
            (TRACE_ID,),
        )
        print(
            f"\n该 trace 涉及的技能调用次数: {dict(skill_total) if skill_total else '无'}",
        )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
