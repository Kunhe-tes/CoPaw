# -*- coding: utf-8 -*-
"""将 RMASSIST seed span 映射到真实技能目录。"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from monitor.app.database import DatabaseConnection, get_database_config


async def repair(source_id: str, apply: bool) -> None:
    """只修复指定 source 下的 seed span。"""
    db = DatabaseConnection(get_database_config())
    await db.connect()
    try:
        skills = await db.fetch_all(
            """
            SELECT skill_id, skill_name, cn_name, description
            FROM (
                SELECT skill_id, skill_name, cn_name, description,
                       ROW_NUMBER() OVER (
                           PARTITION BY skill_id
                           ORDER BY
                               CASE WHEN cn_name IS NOT NULL
                                         AND TRIM(cn_name) <> ''
                                    THEN 0 ELSE 1 END,
                               CASE WHEN enabled = 1 THEN 0 ELSE 1 END,
                               updated_at DESC, id DESC
                       ) AS rn
                FROM swe_skills
                WHERE source_id = %s
                  AND skill_id IS NOT NULL
                  AND TRIM(skill_id) <> ''
            ) ranked
            WHERE rn = 1
            ORDER BY skill_id
            """,
            (source_id,),
        )
        if not skills:
            raise RuntimeError(f"source_id={source_id} 没有可用 swe_skills")

        spans = await db.fetch_all(
            """
            SELECT span_id
            FROM swe_tracing_spans
            WHERE source_id = %s
              AND span_id LIKE 'seed-%%'
            ORDER BY span_id
            """,
            (source_id,),
        )
        updates = []
        for index, span in enumerate(spans):
            skill = skills[index % len(skills)]
            updates.append(
                (skill["skill_id"], skill["skill_name"], span["span_id"]),
            )

        print(f"技能目录: {len(skills)} 条")
        print(f"待修复 seed span: {len(updates)} 条")
        print("示例映射:")
        for skill_id, skill_name, span_id in updates[:10]:
            print(f"  {span_id} -> {skill_id} ({skill_name})")

        if not apply:
            print("仅检查未写入；如确认修复，请追加 --apply")
            return

        written = await db.execute_many(
            """
            UPDATE swe_tracing_spans
            SET skill_id = %s, skill_name = %s
            WHERE span_id = %s
              AND source_id = %s
              AND span_id LIKE 'seed-%%'
            """,
            [(*update, source_id) for update in updates],
        )
        print(f"已修复: {written} 条")
    finally:
        await db.close()


def main() -> None:
    """解析参数并执行修复。"""
    parser = argparse.ArgumentParser(description="修复 RMASSIST seed 技能数据")
    parser.add_argument("--source-id", default="RMASSIST")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(repair(args.source_id, args.apply))


if __name__ == "__main__":
    main()
