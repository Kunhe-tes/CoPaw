# -*- coding: utf-8 -*-
"""重建 rmassistdata 数据库和项目运行表。"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import pymysql

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB_NAME = os.environ.get("COPAW_RESTORE_DB_NAME", "rmassistdata")
DB_HOST = os.environ.get("COPAW_RESTORE_DB_HOST", "120.48.112.239")
DB_PORT = int(os.environ.get("COPAW_RESTORE_DB_PORT", "3306"))
DB_USER = os.environ.get("COPAW_RESTORE_DB_USER", "mysqladmin")
DB_PASSWORD = os.environ.get("COPAW_RESTORE_DB_PASSWORD", "123456")

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "monitor" / "src"))
sys.path.insert(0, str(ROOT / "scheduler" / "src"))


def _connect(database: str | None = None):
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )


def _execute_statements(statements: list[str]) -> None:
    conn = _connect(DB_NAME)
    try:
        with conn.cursor() as cur:
            for statement in statements:
                sql = statement.strip().rstrip(";")
                if not sql:
                    continue
                try:
                    cur.execute(sql)
                except pymysql.MySQLError as exc:
                    code = int(exc.args[0]) if exc.args else 0
                    if code in {1060, 1061, 1068, 1091}:
                        continue
                    raise
        conn.commit()
    finally:
        conn.close()


def _split_sql(text: str) -> list[str]:
    return [
        part.strip()
        for part in text.split(";")
        if part.strip() and not part.lstrip().startswith("--")
    ]


def _create_database() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
            )
        conn.commit()
    finally:
        conn.close()


async def _run_project_initializers() -> None:
    from monitor.app.database.config import MonitorDatabaseConfig
    from monitor.app.database.connection import init_db_connection
    from monitor.app.database.schema import initialize_database
    from scheduler.app.database.connection import (
        init_db_connection as init_scheduler_db_connection,
    )
    from scheduler.app.database.schema import init_database_tables
    from scheduler.config.constant import SchedulerDatabaseConfig
    from swe.app.approvals.store import ApprovalAuditStore
    from swe.app.crons.broadcast_children_store import (
        CronBroadcastChildrenStore,
    )
    from swe.app.crons.broadcast_task_store import CronBroadcastTaskStore
    from swe.app.skill_readiness.store import SkillReadinessStore
    from swe.database.config import DatabaseConfig
    from swe.database.connection import DatabaseConnection

    monitor_db = await init_db_connection(
        MonitorDatabaseConfig(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_connections=1,
            max_connections=2,
        ),
    )
    await initialize_database()

    scheduler_db = await init_scheduler_db_connection(
        SchedulerDatabaseConfig(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_connections=1,
            max_connections=2,
        ),
    )
    await init_database_tables()

    swe_db = DatabaseConnection(
        DatabaseConfig(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_connections=1,
            max_connections=2,
        ),
    )
    await swe_db.connect()
    await ApprovalAuditStore(swe_db).initialize()
    await CronBroadcastChildrenStore(swe_db).initialize()
    await CronBroadcastTaskStore(swe_db).initialize()
    await SkillReadinessStore(swe_db).initialize()
    await swe_db.close()
    await monitor_db.close()
    await scheduler_db.close()


MANUAL_DDL = [
    """
    CREATE TABLE IF NOT EXISTS swe_tracing_traces (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        trace_id VARCHAR(255) NOT NULL UNIQUE,
        b3_trace_id VARCHAR(255) NULL,
        source_id VARCHAR(255) NULL,
        user_id VARCHAR(255) NULL,
        session_id VARCHAR(255) NULL,
        session_name VARCHAR(500) NULL,
        channel VARCHAR(255) NULL,
        start_time DATETIME(6) NOT NULL,
        end_time DATETIME(6) NULL,
        duration_ms INT NULL,
        model_name VARCHAR(255) NULL,
        total_input_tokens INT DEFAULT 0,
        total_output_tokens INT DEFAULT 0,
        total_tokens INT DEFAULT 0,
        tools_used JSON NULL,
        skills_used JSON NULL,
        status VARCHAR(50) DEFAULT 'running',
        error TEXT NULL,
        user_message LONGTEXT NULL,
        user_name VARCHAR(255) NULL,
        bbk_id VARCHAR(255) NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_source_id (source_id),
        INDEX idx_user_id (user_id),
        INDEX idx_session_id (session_id),
        INDEX idx_start_time (start_time),
        INDEX idx_status (status),
        INDEX idx_b3_trace_id (b3_trace_id),
        INDEX idx_bbk_id (bbk_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS swe_tracing_spans (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        span_id VARCHAR(255) NOT NULL UNIQUE,
        trace_id VARCHAR(255) NOT NULL,
        source_id VARCHAR(255) NULL,
        name VARCHAR(500) NOT NULL,
        event_type VARCHAR(100) NOT NULL,
        start_time DATETIME(6) NOT NULL,
        end_time DATETIME(6) NULL,
        duration_ms INT NULL,
        user_id VARCHAR(255) NULL,
        session_id VARCHAR(255) NULL,
        channel VARCHAR(255) NULL,
        model_name VARCHAR(255) NULL,
        input_tokens INT DEFAULT 0,
        output_tokens INT DEFAULT 0,
        tool_name VARCHAR(255) NULL,
        skill_name VARCHAR(255) NULL,
        skill_id VARCHAR(128) DEFAULT '',
        mcp_server VARCHAR(255) NULL,
        tool_input LONGTEXT NULL,
        tool_output LONGTEXT NULL,
        error TEXT NULL,
        user_name VARCHAR(255) NULL,
        bbk_id VARCHAR(255) NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_trace_id (trace_id),
        INDEX idx_source_id (source_id),
        INDEX idx_event_type (event_type),
        INDEX idx_start_time (start_time),
        INDEX idx_user_id (user_id),
        INDEX idx_session_id (session_id),
        INDEX idx_tool_name (tool_name),
        INDEX idx_skill_name (skill_name),
        INDEX idx_skill_id (skill_id),
        INDEX idx_bbk_id (bbk_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS swe_high_frequency_question_result (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        batch_id VARCHAR(64) NOT NULL,
        source_id VARCHAR(64) NOT NULL,
        question TEXT NOT NULL,
        frequency INT NOT NULL DEFAULT 0,
        related_questions JSON NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_batch_source (batch_id, source_id),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def _apply_migrations() -> None:
    for path in [
        ROOT / "deploy" / "migrations" / "2026_06_22_add_swe_skills_table.sql",
        ROOT
        / "deploy"
        / "migrations"
        / "2026_07_29_add_swe_market_skills_table.sql",
    ]:
        _execute_statements(_split_sql(path.read_text(encoding="utf-8")))


def _verify() -> None:
    conn = _connect(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (DB_NAME,),
            )
            total = cur.fetchone()[0]
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name IN (
                    'swe_tracing_traces',
                    'swe_tracing_spans',
                    'swe_skills',
                    'swe_marketplace_skills',
                    'swe_cron_jobs',
                    'swe_cron_executions'
                  )
                """,
                (DB_NAME,),
            )
            present = sorted(row[0] for row in cur.fetchall())
    finally:
        conn.close()
    print(f"database={DB_NAME}")
    print(f"table_count={total}")
    print("core_tables=" + ",".join(present))


async def main() -> None:
    _create_database()
    await _run_project_initializers()
    _execute_statements(MANUAL_DDL)
    _apply_migrations()
    _verify()


if __name__ == "__main__":
    asyncio.run(main())
