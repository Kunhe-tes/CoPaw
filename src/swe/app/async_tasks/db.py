# -*- coding: utf-8 -*-
"""异步任务写库所需的数据库连接获取工具。"""

from __future__ import annotations

from typing import Any

from ...database import DatabaseConnection, get_database_config


async def get_or_create_async_task_db(request: Any) -> Any | None:
    """从 app state 获取数据库连接，缺失时按 SWE_DB 配置懒加载。"""
    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    if state is None:
        return None

    db_connection = getattr(state, "db_connection", None)
    if db_connection is not None:
        return db_connection

    database_config = get_database_config()
    if not database_config.host or database_config.host == "localhost":
        return None

    db_connection = DatabaseConnection(database_config)
    await db_connection.connect()
    state.db_connection = db_connection
    return db_connection
