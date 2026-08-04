# -*- coding: utf-8 -*-
"""调查指定 trace_id 在技能排行榜中未展示的原因."""

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
        print(f"=== trace_id = {TRACE_ID} ===\n")

        # 1) 关联 trace
        trace_rows = await db.fetch_all(
            """
            SELECT trace_id, source_id, user_id, user_name, bbk_id, session_id,
                   start_time, end_time, duration_ms, status
            FROM swe_tracing_traces
            WHERE trace_id = %s
            """,
            (TRACE_ID,),
        )
        print(f"swe_tracing_traces 匹配: {len(trace_rows)} 条")
        for r in trace_rows:
            print(f"  {dict(r)}\n")

        # 2) 关联 spans
        span_rows = await db.fetch_all(
            """
            SELECT span_id, source_id, name, event_type, skill_name, skill_id,
                   user_id, bbk_id, session_id, start_time, duration_ms, error
            FROM swe_tracing_spans
            WHERE trace_id = %s
            ORDER BY start_time ASC, span_id ASC
            """,
            (TRACE_ID,),
        )
        print(f"\nswe_tracing_spans 匹配: {len(span_rows)} 条")
        for r in span_rows:
            print(
                f"  span_id={r['span_id']} | event_type={r['event_type']} | "
                f"skill_name={r['skill_name']!r} | skill_id={r['skill_id']!r} | "
                f"user_id={r['user_id']!r} | bbk_id={r['bbk_id']!r} | "
                f"start_time={r['start_time']} | duration_ms={r['duration_ms']}",
            )

        # 3) 如果有 skill_name,看 swe_skills 映射情况
        skill_names = sorted(
            {r["skill_name"] for r in span_rows if r.get("skill_name")},
        )
        if skill_names:
            print("\n=== skill_name 候选映射 ===")
            placeholders = ", ".join(["%s"] * len(skill_names))
            skill_rows = await db.fetch_all(
                f"""
                SELECT skill_id, skill_name, cn_name, enabled
                FROM swe_skills
                WHERE skill_name IN ({placeholders})
                ORDER BY skill_name, id
                """,
                tuple(skill_names),
            )
            print(f"swe_skills 匹配: {len(skill_rows)} 条")
            for r in skill_rows:
                print(f"  {dict(r)}")
        else:
            print("\n所有 span 都没有 skill_name")

        # 4) source 分布
        if span_rows:
            sources = {r["source_id"] for r in span_rows}
            print(f"\nsource_id 分布: {sources}")
            # 看 EXCLUDED_SOURCE_IDS 是否排除了它
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
