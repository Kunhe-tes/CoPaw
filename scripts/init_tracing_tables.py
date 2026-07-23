# -*- coding: utf-8 -*-
"""创建 tracing 表并初始化测试数据."""

import asyncio
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swe.database import DatabaseConnection, get_database_config


async def _create_traces_table(db: DatabaseConnection) -> None:
    """创建 swe_tracing_traces 表."""
    create_traces_sql = """
    CREATE TABLE IF NOT EXISTS `swe_tracing_traces` (
        `id` BIGINT AUTO_INCREMENT COMMENT '自增主键',
        `trace_id` VARCHAR(36) NOT NULL COMMENT '追踪唯一标识',
        `b3_trace_id` VARCHAR(64) DEFAULT NULL COMMENT 'Upstream B3 trace identifier',
        `source_id` VARCHAR(64) NOT NULL COMMENT '数据源标识',
        `user_id` VARCHAR(128) DEFAULT NULL COMMENT '用户ID',
        `user_name` VARCHAR(256) DEFAULT NULL COMMENT '用户名称',
        `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK标识符',
        `session_id` VARCHAR(36) DEFAULT NULL COMMENT '会话标识',
        `channel` VARCHAR(32) DEFAULT NULL COMMENT '通道来源',
        `start_time` DATETIME DEFAULT NULL COMMENT '开始时间',
        `end_time` DATETIME DEFAULT NULL COMMENT '结束时间',
        `duration_ms` INT DEFAULT NULL COMMENT '耗时毫秒',
        `model_name` VARCHAR(64) DEFAULT NULL COMMENT '模型名称',
        `total_input_tokens` INT DEFAULT 0 COMMENT '输入Token',
        `total_output_tokens` INT DEFAULT 0 COMMENT '输出Token',
        `total_tokens` INT DEFAULT 0 COMMENT '总Token',
        `tools_used` JSON DEFAULT NULL COMMENT '工具列表',
        `skills_used` JSON DEFAULT NULL COMMENT '技能列表',
        `status` VARCHAR(16) DEFAULT 'running' COMMENT '状态',
        `error` TEXT DEFAULT NULL COMMENT '错误信息',
        `user_message` TEXT DEFAULT NULL COMMENT '用户消息',
        PRIMARY KEY (`id`),
        UNIQUE KEY `uk_trace_id` (`trace_id`),
        INDEX `idx_source_id` (`source_id`),
        INDEX `idx_source_b3_trace` (`source_id`, `b3_trace_id`),
        INDEX `idx_source_start_time` (`source_id`, `start_time`),
        INDEX `idx_source_user` (`source_id`, `user_id`),
        INDEX `idx_start_time` (`start_time`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='追踪记录表'
    """
    await db.execute(create_traces_sql)
    print("swe_tracing_traces 表创建成功")


async def _create_spans_table(db: DatabaseConnection) -> None:
    """创建 swe_tracing_spans 表."""
    create_spans_sql = """
    CREATE TABLE IF NOT EXISTS `swe_tracing_spans` (
        `id` BIGINT AUTO_INCREMENT COMMENT '自增主键',
        `span_id` VARCHAR(36) NOT NULL COMMENT 'Span唯一标识',
        `trace_id` VARCHAR(36) NOT NULL COMMENT '所属追踪ID',
        `source_id` VARCHAR(64) NOT NULL COMMENT '数据源标识',
        `name` VARCHAR(128) DEFAULT NULL COMMENT 'Span名称',
        `event_type` VARCHAR(32) NOT NULL COMMENT '事件类型',
        `start_time` DATETIME NOT NULL COMMENT '开始时间',
        `end_time` DATETIME DEFAULT NULL COMMENT '结束时间',
        `duration_ms` INT DEFAULT NULL COMMENT '耗时毫秒',
        `user_id` VARCHAR(128) DEFAULT '' COMMENT '用户ID',
        `user_name` VARCHAR(256) DEFAULT NULL COMMENT '用户名称',
        `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK标识符',
        `session_id` VARCHAR(36) DEFAULT '' COMMENT '会话标识',
        `channel` VARCHAR(32) DEFAULT '' COMMENT '通道来源',
        `model_name` VARCHAR(64) DEFAULT NULL COMMENT '模型名称',
        `input_tokens` INT DEFAULT NULL COMMENT '输入Token',
        `output_tokens` INT DEFAULT NULL COMMENT '输出Token',
        `tool_name` VARCHAR(64) DEFAULT NULL COMMENT '工具名称',
        `skill_name` VARCHAR(128) DEFAULT NULL COMMENT '技能名称',
        `mcp_server` VARCHAR(64) DEFAULT NULL COMMENT 'MCP服务器名',
        `tool_input` JSON DEFAULT NULL COMMENT '工具输入',
        `tool_output` TEXT DEFAULT NULL COMMENT '工具输出',
        `error` TEXT DEFAULT NULL COMMENT '错误信息',
        PRIMARY KEY (`id`),
        UNIQUE KEY `uk_span_id` (`span_id`),
        INDEX `idx_trace_id` (`trace_id`),
        INDEX `idx_source_id` (`source_id`),
        INDEX `idx_source_start_time` (`source_id`, `start_time`),
        INDEX `idx_source_trace` (`source_id`, `trace_id`),
        INDEX `idx_source_user` (`source_id`, `user_id`),
        INDEX `idx_source_skill` (`source_id`, `event_type`, `skill_name`),
        INDEX `idx_event_type` (`event_type`),
        INDEX `idx_skill_name` (`skill_name`),
        INDEX `idx_mcp_server` (`mcp_server`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Span记录表'
    """
    await db.execute(create_spans_sql)
    print("swe_tracing_spans 表创建成功")


async def _create_operation_logs_table(db: DatabaseConnection) -> None:
    """创建操作日志表."""
    create_logs_sql = """
    CREATE TABLE IF NOT EXISTS `swe_marketplace_operation_logs` (
        `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
        `source_id` VARCHAR(64) NOT NULL,
        `operator_id` VARCHAR(64) NOT NULL,
        `operator_name` VARCHAR(256) DEFAULT NULL,
        `operation` VARCHAR(32) NOT NULL,
        `item_type` VARCHAR(16) NOT NULL,
        `item_id` VARCHAR(64) NOT NULL,
        `item_name` VARCHAR(256) DEFAULT NULL,
        `target_user_id` VARCHAR(64) DEFAULT NULL,
        `target_user_name` VARCHAR(256) DEFAULT NULL,
        `target_bbk_id` VARCHAR(64) DEFAULT NULL,
        `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX `idx_source_id` (`source_id`),
        INDEX `idx_item_id` (`item_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='市场操作日志'
    """
    await db.execute(create_logs_sql)
    print("swe_marketplace_operation_logs 表创建成功")


async def _init_skill_test_data(
    db: DatabaseConnection,
    source_id: str,
    test_skills: list[str],
    test_users: list[tuple[str, str, str]],
) -> None:
    """初始化技能调用测试数据."""
    now = datetime.now()
    traces_data: list[tuple] = []
    spans_data: list[tuple] = []

    for day_offset in range(7):
        day = now - timedelta(days=day_offset)
        for user_id, user_name, bbk_id in test_users:
            num_sessions = random.randint(1, 5)
            for _ in range(num_sessions):
                trace_id = str(uuid.uuid4())
                session_id = str(uuid.uuid4())
                start_time = day.replace(
                    hour=random.randint(9, 18),
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59),
                )
                end_time = start_time + timedelta(
                    seconds=random.randint(30, 300),
                )
                duration_ms = int(
                    (end_time - start_time).total_seconds() * 1000,
                )
                used_skills = random.sample(test_skills, random.randint(1, 3))

                traces_data.append(
                    (
                        trace_id,
                        source_id,
                        user_id,
                        user_name,
                        bbk_id,
                        session_id,
                        "console",
                        start_time,
                        end_time,
                        duration_ms,
                        "claude-3-5-sonnet",
                        random.randint(100, 2000),
                        random.randint(100, 1000),
                        random.randint(200, 3000),
                        "[]",
                        json.dumps(used_skills),
                        "completed",
                        None,
                        f"测试消息 - {day.strftime('%Y-%m-%d')}",
                    ),
                )

                for skill_name in used_skills:
                    span_id = str(uuid.uuid4())
                    skill_start = start_time + timedelta(
                        seconds=random.randint(5, 50),
                    )
                    skill_duration = random.randint(100, 5000)
                    skill_end = skill_start + timedelta(
                        milliseconds=skill_duration,
                    )

                    spans_data.append(
                        (
                            span_id,
                            trace_id,
                            source_id,
                            f"skill_{skill_name}",
                            "skill_invocation",
                            skill_start,
                            skill_end,
                            skill_duration,
                            user_id,
                            user_name,
                            bbk_id,
                            session_id,
                            "console",
                            None,
                            None,
                            None,
                            None,
                            skill_name,
                            None,
                            None,
                            None,
                            None,
                        ),
                    )

    print(f"插入 {len(traces_data)} 条 trace 记录...")
    insert_trace_sql = """
        INSERT INTO swe_tracing_traces
            (trace_id, source_id, user_id, user_name, bbk_id, session_id, channel,
             start_time, end_time, duration_ms, model_name,
             total_input_tokens, total_output_tokens, total_tokens,
             tools_used, skills_used, status, error, user_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    await db.execute_many(insert_trace_sql, traces_data)

    print(f"插入 {len(spans_data)} 条 span 记录...")
    insert_span_sql = """
        INSERT INTO swe_tracing_spans
            (span_id, trace_id, source_id, name, event_type, start_time, end_time, duration_ms,
             user_id, user_name, bbk_id, session_id, channel, model_name,
             input_tokens, output_tokens, tool_name, skill_name, mcp_server,
             tool_input, tool_output, error)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    await db.execute_many(insert_span_sql, spans_data)


async def _init_mcp_test_data(
    db: DatabaseConnection,
    source_id: str,
    test_users: list[tuple[str, str, str]],
    test_mcp_servers: list[str],
) -> None:
    """初始化 MCP 调用测试数据."""
    now = datetime.now()
    mcp_spans_data: list[tuple] = []

    for day_offset in range(7):
        day = now - timedelta(days=day_offset)
        for user_id, user_name, bbk_id in test_users[:3]:
            num_calls = random.randint(1, 3)
            for _ in range(num_calls):
                span_id = str(uuid.uuid4())
                trace_id = str(uuid.uuid4())
                session_id = str(uuid.uuid4())
                mcp_server = random.choice(test_mcp_servers)
                start_time = day.replace(
                    hour=random.randint(9, 18),
                    minute=random.randint(0, 59),
                )
                duration_ms = random.randint(50, 500)

                mcp_spans_data.append(
                    (
                        span_id,
                        trace_id,
                        source_id,
                        f"mcp_{mcp_server}",
                        "tool_call_end",
                        start_time,
                        start_time + timedelta(milliseconds=duration_ms),
                        duration_ms,
                        user_id,
                        user_name,
                        bbk_id,
                        session_id,
                        "console",
                        None,
                        None,
                        None,
                        None,
                        mcp_server,
                        None,
                        None,
                        None,
                    ),
                )

    print(f"插入 {len(mcp_spans_data)} 条 MCP span 记录...")
    insert_mcp_span_sql = """
        INSERT INTO swe_tracing_spans
            (span_id, trace_id, source_id, name, event_type, start_time, end_time, duration_ms,
             user_id, user_name, bbk_id, session_id, channel, model_name,
             input_tokens, output_tokens, skill_name, mcp_server,
             tool_input, tool_output, error)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    await db.execute_many(insert_mcp_span_sql, mcp_spans_data)


async def _verify_skill_stats(db: DatabaseConnection) -> None:
    """验证技能统计数据."""
    stats_sql = """
        SELECT source_id, skill_name, COUNT(*) as call_count, COUNT(DISTINCT user_id) as user_count
        FROM swe_tracing_spans
        WHERE event_type = 'skill_invocation'
        GROUP BY source_id, skill_name
        ORDER BY call_count DESC
    """
    rows = await db.fetch_all(stats_sql)
    print("技能统计数据:")
    for row in rows:
        print(
            f"  source_id={row['source_id']}, skill_name={row['skill_name']}, "
            f"call_count={row['call_count']}, user_count={row['user_count']}",
        )


async def _verify_mcp_stats(db: DatabaseConnection, source_id: str) -> None:
    """验证 MCP 统计数据."""
    mcp_stats_sql = """
        SELECT mcp_server, COUNT(*) as call_count, COUNT(DISTINCT user_id) as user_count
        FROM swe_tracing_spans
        WHERE mcp_server IS NOT NULL AND source_id = %s
        GROUP BY mcp_server
        ORDER BY call_count DESC
    """
    mcp_rows = await db.fetch_all(mcp_stats_sql, (source_id,))
    print("MCP 统计数据:")
    for row in mcp_rows:
        print(
            f"  mcp_server={row['mcp_server']}, call_count={row['call_count']}, "
            f"user_count={row['user_count']}",
        )


async def create_tables_and_init_data():
    """执行建表和数据初始化."""
    db_config = get_database_config()
    print(
        f"数据库配置: host={db_config.host}, port={db_config.port}, "
        f"db={db_config.database}",
    )

    db = DatabaseConnection(db_config)
    try:
        await db.connect()
        print(f"数据库连接状态: {db.is_connected}")

        if not db.is_connected:
            print("数据库未连接，无法执行")
            return

        # 创建表
        print("\n=== 创建表 ===")
        await _create_traces_table(db)
        await _create_spans_table(db)
        await _create_operation_logs_table(db)

        # 测试数据配置
        source_id = "portal"
        test_skills = ["xlsx", "pdf", "data_analysis", "report_generator"]
        test_users = [
            ("user_001", "张三", "bbk_100"),
            ("user_002", "李四", "bbk_100"),
            ("user_003", "王五", "bbk_200"),
            ("user_004", "赵六", "bbk_200"),
            ("user_005", "钱七", "bbk_300"),
        ]
        test_mcp_servers = ["weather_server", "stock_server", "map_server"]

        # 初始化测试数据
        print("\n=== 初始化技能测试数据 ===")
        await _init_skill_test_data(db, source_id, test_skills, test_users)

        # 验证技能统计
        print("\n=== 验证技能统计数据 ===")
        await _verify_skill_stats(db)

        # 初始化 MCP 测试数据
        print("\n=== 初始化 MCP 测试数据 ===")
        await _init_mcp_test_data(db, source_id, test_users, test_mcp_servers)

        # 验证 MCP 统计
        await _verify_mcp_stats(db, source_id)

        print("\n=== 全部完成 ===")

    except Exception as e:
        print(f"执行失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(create_tables_and_init_data())
