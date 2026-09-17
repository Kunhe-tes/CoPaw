# -*- coding: utf-8 -*-
"""列出所有 fill-metadata 变体."""

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
            SELECT id, source_id, skill_id, skill_name, cn_name, description,
                   enabled, updated_at
            FROM swe_skills
            WHERE source_id = 'RMASSIST'
              AND skill_name = 'fill-metadata'
            ORDER BY id
            """,
        )
        print(f"fill-metadata 记录数: {len(rows)}\n")
        for row in rows:
            print(
                f"id={row['id']} | skill_id={row['skill_id']} | "
                f"cn_name={row['cn_name']!r} | enabled={row['enabled']} | "
                f"updated_at={row['updated_at']}",
            )
            if row["description"]:
                print(f"  description: {row['description'][:100]}...")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
