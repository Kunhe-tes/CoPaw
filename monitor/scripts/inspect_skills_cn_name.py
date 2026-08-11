# -*- coding: utf-8 -*-
"""查询 swe_skills 中需要补 cn_name 的记录。"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from monitor.app.database import DatabaseConnection, get_database_config


async def main() -> None:
    db = DatabaseConnection(get_database_config())
    await db.connect()
    try:
        rows = await db.fetch_all(
            """
            SELECT skill_id, skill_name, cn_name, enabled, updated_at
            FROM swe_skills
            WHERE source_id = 'RMASSIST'
              AND skill_id IS NOT NULL
              AND TRIM(skill_id) <> ''
              AND (
                  cn_name IS NULL
                  OR TRIM(cn_name) = ''
                  OR cn_name REGEXP '^[A-Za-z0-9 _-]+$'
              )
            ORDER BY skill_name, cn_name
            """,
        )
        print(f"待检查 swe_skills: {len(rows)} 条\n")
        for row in rows:
            print(
                f"  skill_id={row['skill_id']} | "
                f"skill_name={row['skill_name']} | "
                f"cn_name={row['cn_name']!r}",
            )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
