# -*- coding: utf-8 -*-
"""执行数据库迁移脚本"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from swe.database.config import get_database_config
from swe.database.connection import DatabaseConnection


async def run_migration():
    """执行迁移"""
    config = get_database_config()
    db = DatabaseConnection(config)

    await db.connect()

    migration_sql = """
        ALTER TABLE `swe_tracing_spans`
        ADD COLUMN `skill_description` TEXT DEFAULT NULL COMMENT '技能描述，从 SKILL.md 的 description 字段读取'
        AFTER `skill_name`;
    """

    try:
        await db.execute(migration_sql)
        print(
            "Migration completed successfully: skill_description column added.",
        )
    except Exception as e:
        if "Duplicate column name" in str(e):
            print("Column skill_description already exists, skipping.")
        else:
            print(f"Migration failed: {e}")
            raise
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(run_migration())
