# -*- coding: utf-8 -*-
"""列出所有 swe_skills 用于核对中文名."""

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
            SELECT id, source_id, skill_id, skill_name, cn_name, description, enabled
            FROM swe_skills
            WHERE source_id = 'RMASSIST'
              AND skill_id IS NOT NULL
              AND TRIM(skill_id) <> ''
              AND (
                  cn_name IS NULL
                  OR TRIM(cn_name) = ''
                  OR cn_name REGEXP '^[A-Za-z0-9 _-]+$'
              )
            ORDER BY skill_name
            """,
        )
        print(f"待补 cn_name 的 swe_skills: {len(rows)}\n")
        for row in rows:
            print(
                f"id={row['id']} | "
                f"skill_id={row['skill_id']} | "
                f"skill_name={row['skill_name']} | "
                f"cn_name={row['cn_name']!r} | "
                f"description={row['description']!r} | "
                f"enabled={row['enabled']}",
            )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
