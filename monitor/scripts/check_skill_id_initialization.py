# -*- coding: utf-8 -*-
"""检查历史 span skill_id 初始化接口的数据条件。"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

MONITOR_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = MONITOR_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from monitor.app.database import DatabaseConnection, get_database_config


async def verify_existing_skill_ids(
    db: DatabaseConnection,
    source_id: str,
) -> None:
    """按初始化服务的候选优先级核对已有 skill_id。"""
    spans = await db.fetch_all(
        """
        SELECT span_id, skill_name, skill_id, start_time
        FROM swe_tracing_spans
        WHERE source_id = %s
          AND span_id NOT LIKE 'seed-%%'
          AND skill_name IS NOT NULL
          AND TRIM(skill_name) <> ''
        ORDER BY start_time ASC, span_id ASC
        """,
        (source_id,),
    )
    candidates = await db.fetch_all(
        """
        SELECT id, skill_name, skill_id, cn_name, enabled, updated_at
        FROM swe_skills
        WHERE source_id = %s
          AND skill_id IS NOT NULL
          AND TRIM(skill_id) <> ''
        ORDER BY
          CASE WHEN cn_name IS NOT NULL AND TRIM(cn_name) <> '' THEN 0 ELSE 1 END ASC,
          CASE WHEN enabled = 1 THEN 0 ELSE 1 END ASC,
          updated_at DESC,
          id DESC,
          skill_name,
          skill_id
        """,
        (source_id,),
    )
    expected_by_name = {}
    candidate_ids_by_name = {}
    for row in candidates:
        expected_by_name.setdefault(row["skill_name"], row["skill_id"])
        candidate_ids_by_name.setdefault(row["skill_name"], set()).add(
            row["skill_id"],
        )

    matched = []
    mismatched = []
    unmatched = []
    for span in spans:
        expected = expected_by_name.get(span["skill_name"])
        if expected is None:
            unmatched.append(span)
        elif span["skill_id"] == expected:
            matched.append(span)
        else:
            mismatched.append((span, expected))

    excluded_row = await db.fetch_one(
        "SELECT COUNT(*) AS count FROM swe_tracing_spans "
        "WHERE source_id = %s AND span_id LIKE 'seed-%%'",
        (source_id,),
    )

    print("\n=== 已有 skill_id 正确性检查（已排除 seed-*） ===")
    print(f"排除的 seed 测试 span: {excluded_row['count']}")
    print(f"有有效 skill_name 的 span: {len(spans)}")
    print(f"与稳定选择结果一致: {len(matched)}")
    print(f"swe_skills 无候选: {len(unmatched)}")
    print(f"与稳定选择结果不一致: {len(mismatched)}")
    ambiguous_names = {
        name for name, ids in candidate_ids_by_name.items() if len(ids) > 1
    }
    print(f"存在多个不同 skill_id 的 skill_name: {len(ambiguous_names)}")

    if unmatched:
        print("无候选样本:")
        for span in unmatched[:20]:
            print(
                f"  span_id={span['span_id']}, "
                f"skill_name={span['skill_name']}, "
                f"skill_id={span['skill_id']}",
            )
    if mismatched:
        print("不一致样本:")
        for span, expected in mismatched[:20]:
            print(
                f"  span_id={span['span_id']}, "
                f"skill_name={span['skill_name']}, "
                f"当前={span['skill_id']}, 期望={expected}",
            )


async def check(source_id: str, limit: int) -> None:
    """使用 Monitor 实际配置逐层检查待初始化数据。"""
    config = get_database_config()
    db = DatabaseConnection(config)
    print(
        f"数据库: {config.user}@{config.host}:{config.port}/{config.database}",
    )
    print(f"source_id: {source_id}")

    await db.connect()
    try:
        database = await db.fetch_one("SELECT DATABASE() AS database_name")
        print(f"当前数据库: {database['database_name']}")

        checks = [
            (
                "该 source 的全部 span",
                "SELECT COUNT(*) AS count FROM swe_tracing_spans "
                "WHERE source_id = %s",
            ),
            (
                "skill_id 为空的 span",
                "SELECT COUNT(*) AS count FROM swe_tracing_spans "
                "WHERE source_id = %s "
                "AND (skill_id IS NULL OR TRIM(skill_id) = '')",
            ),
            (
                "可初始化的 span",
                "SELECT COUNT(*) AS count FROM swe_tracing_spans "
                "WHERE source_id = %s "
                "AND (skill_id IS NULL OR TRIM(skill_id) = '') "
                "AND skill_name IS NOT NULL AND TRIM(skill_name) <> ''",
            ),
        ]
        for label, sql in checks:
            row = await db.fetch_one(sql, (source_id,))
            print(f"{label}: {row['count']}")

        scan_rows = await db.fetch_all(
            """
            SELECT span_id, source_id, skill_name, skill_id, start_time
            FROM swe_tracing_spans
            WHERE (start_time, span_id) > (%s, %s)
              AND (skill_id IS NULL OR TRIM(skill_id) = '')
              AND skill_name IS NOT NULL
              AND TRIM(skill_name) <> ''
              AND source_id = %s
            ORDER BY start_time ASC, span_id ASC
            LIMIT %s
            """,
            (datetime(1000, 1, 1), "", source_id, limit),
        )
        print(f"初始化接口首批扫描结果: {len(scan_rows)}")
        for row in scan_rows[:10]:
            print(
                "  "
                f"span_id={row['span_id']}, "
                f"skill_name={row['skill_name']}, "
                f"start_time={row['start_time']}",
            )

        if scan_rows:
            skill_names = sorted({row["skill_name"] for row in scan_rows})
            placeholders = ", ".join(["%s"] * len(skill_names))
            candidates = await db.fetch_all(
                f"""
                SELECT skill_name, COUNT(*) AS candidate_count,
                       COUNT(DISTINCT skill_id) AS distinct_skill_ids
                FROM swe_skills
                WHERE source_id = %s
                  AND skill_name IN ({placeholders})
                  AND skill_id IS NOT NULL
                  AND TRIM(skill_id) <> ''
                GROUP BY skill_name
                ORDER BY skill_name
                """,
                tuple([source_id, *skill_names]),
            )
            print("首批 skill_name 的技能候选:")
            if not candidates:
                print("  swe_skills 中没有匹配候选")
            for row in candidates:
                print(
                    "  "
                    f"skill_name={row['skill_name']}, "
                    f"候选记录={row['candidate_count']}, "
                    f"不同 skill_id={row['distinct_skill_ids']}",
                )

        source_rows = await db.fetch_all(
            "SELECT source_id, COUNT(*) AS count FROM swe_skills "
            "GROUP BY source_id ORDER BY count DESC",
        )
        print("\nswe_skills source_id 分布:")
        for row in source_rows:
            print(f"  {row['source_id']}: {row['count']}")

        await verify_existing_skill_ids(db, source_id)
    finally:
        await db.close()


def main() -> None:
    """解析命令行参数并执行检查。"""
    parser = argparse.ArgumentParser(
        description="检查历史 span skill_id 初始化条件",
    )
    parser.add_argument("--source-id", default="RMASSIST")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(check(args.source_id, args.limit))


if __name__ == "__main__":
    main()
