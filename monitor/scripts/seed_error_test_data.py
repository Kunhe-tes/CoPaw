# -*- coding: utf-8 -*-
"""生成报错分析测试数据。

为 swe_tracing_spans 表插入带有 error 字段的测试数据，
覆盖 llm_input（模型报错）和 tool_call_end（工具报错）两种类型。

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_error_test_data.py
"""

import asyncio
import json
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def load_db_config_from_env_file() -> dict[str, Any]:
    """从用户 envs.json 或环境变量加载数据库配置."""
    import os

    envs_file = Path(os.path.expanduser("~")) / ".swe.secret" / "envs.json"
    if envs_file.exists():
        with open(envs_file, encoding="utf-8") as f:
            env_config = json.load(f)
            password = env_config.get("SWE_DB_ACCESS", "")
            if password.startswith("BEE_"):
                password = password[4:]
            return {
                "host": env_config.get("SWE_DB_HOST", "localhost"),
                "port": int(env_config.get("SWE_DB_PORT", 3306)),
                "user": env_config.get("SWE_DB_USER", "root"),
                "password": password,
                "database": env_config.get("SWE_DB_NAME", "monitor"),
            }
    password = os.environ.get("MONITOR_DB_ACCESS", "")
    if password.startswith("BEE_"):
        password = password[4:]
    return {
        "host": os.environ.get("MONITOR_DB_HOST", "localhost"),
        "port": int(os.environ.get("MONITOR_DB_PORT", 3306)),
        "user": os.environ.get("MONITOR_DB_USER", "root"),
        "password": password,
        "database": os.environ.get("MONITOR_DB_NAME", "monitor"),
    }


from monitor.app.database.config import MonitorDatabaseConfig
from monitor.app.database.connection import DatabaseConnection

BBK_IDS = ["100", "200", "201", "202", "203", "V00"]
SOURCE_IDS = ["SZLS", "CMSJY", "UPPCLAW", "copilotClaw", "ruice"]
MODELS = ["gpt-4", "claude-3", "glm-4", "qwen-2"]
TOOL_NAMES = [
    "sql_query",
    "file_read",
    "python_executor",
    "web_search",
    "chart_generator",
]

# 报错信息池
MODEL_ERRORS = [
    "Connection timeout to model provider",
    "Invalid API key for model service",
    "Model response parsing error: unexpected token",
    "Rate limit exceeded for model API",
    "Model context length exceeded",
    "Model service unavailable: 503",
]

TOOL_ERRORS = [
    "Database connection refused: timeout after 30s",
    "File not found: /data/reports/2026/q1.xlsx",
    "Python execution error: NameError - undefined variable",
    "Web search API returned 403 Forbidden",
    "Chart rendering failed: invalid data format",
    "MCP server connection dropped",
]


async def main():
    """生成报错分析测试数据."""
    db_config = load_db_config_from_env_file()
    if not db_config:
        print("错误: 无法从 prd.json 加载数据库配置")
        return

    config = MonitorDatabaseConfig(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
    )
    print(f"数据库: {config.host}:{config.port}/{config.database}")

    db = DatabaseConnection(config)
    await db.connect()
    print("数据库连接成功\n")

    try:
        # 清理旧测试数据
        await db.execute(
            "DELETE FROM swe_tracing_spans WHERE trace_id LIKE 'test-error-%'",
        )
        print("已清理旧测试数据\n")

        start_date = datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) - timedelta(days=29)
        end_date = datetime.now()

        insert_count = 0
        insert_sql = """
            INSERT INTO swe_tracing_spans (
                span_id, trace_id, source_id, name, event_type,
                start_time, end_time, duration_ms, user_id, user_name,
                bbk_id, session_id, channel, model_name, input_tokens,
                output_tokens, tool_name, skill_name, mcp_server, error
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        # 为每个 source_id 分别生成模型报错和工具报错
        model_errors_per_source = 24  # 24 * 5 = 120 条模型报错
        tool_errors_per_source = 16  # 16 * 5 = 80 条工具报错

        batches = []

        for source_id in SOURCE_IDS:
            # 模型报错
            for _ in range(model_errors_per_source):
                trace_id = f"test-error-{uuid.uuid4().hex[:10]}"
                start_time = start_date + timedelta(
                    seconds=random.randint(
                        0,
                        int((end_date - start_date).total_seconds()),
                    ),
                )
                duration = random.randint(5000, 30000)
                end_time = start_time + timedelta(milliseconds=duration)

                batches.append(
                    (
                        uuid.uuid4().hex,
                        trace_id,
                        source_id,
                        "model inference",
                        "llm_input",
                        start_time,
                        end_time,
                        duration,
                        f"user-{random.randint(10000, 99999)}",
                        f"用户{random.randint(1, 50)}",
                        random.choice(BBK_IDS),
                        uuid.uuid4().hex[:16],
                        random.choice(["console", "api", "web"]),
                        random.choice(MODELS),
                        random.randint(100, 5000),
                        None,
                        None,
                        None,
                        None,
                        random.choice(MODEL_ERRORS),
                    ),
                )

            # 工具报错
            for _ in range(tool_errors_per_source):
                trace_id = f"test-error-{uuid.uuid4().hex[:10]}"
                start_time = start_date + timedelta(
                    seconds=random.randint(
                        0,
                        int((end_date - start_date).total_seconds()),
                    ),
                )
                duration = random.randint(1000, 15000)
                end_time = start_time + timedelta(milliseconds=duration)
                tool_name = random.choice(TOOL_NAMES)

                batches.append(
                    (
                        uuid.uuid4().hex,
                        trace_id,
                        source_id,
                        f"{tool_name} execution",
                        "tool_call_end",
                        start_time,
                        end_time,
                        duration,
                        f"user-{random.randint(10000, 99999)}",
                        f"用户{random.randint(1, 50)}",
                        random.choice(BBK_IDS),
                        uuid.uuid4().hex[:16],
                        random.choice(["console", "api", "web"]),
                        None,
                        None,
                        None,
                        tool_name,
                        None,
                        None,
                        random.choice(TOOL_ERRORS),
                    ),
                )

        # 批量插入
        batch_size = 100
        for i in range(0, len(batches), batch_size):
            chunk = batches[i : i + batch_size]
            await db.execute_many(insert_sql, chunk)
            insert_count += len(chunk)
            print(f"  已插入 {insert_count}/{len(batches)} 条")

        print(f"\n共插入 {insert_count} 条报错数据")
        print(
            f"时间范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
        )

        # 验证
        print("\n=== 报错类型分布 ===")
        rows = await db.fetch_all("""
            SELECT event_type, COUNT(*) as cnt
            FROM swe_tracing_spans
            WHERE trace_id LIKE 'test-error-%'
              AND error IS NOT NULL
              AND error != ''
            GROUP BY event_type
            ORDER BY cnt DESC
        """)
        for row in rows:
            label = (
                "模型报错" if row["event_type"] == "llm_input" else "工具报错"
            )
            print(f"  {label} ({row['event_type']}): {row['cnt']} 条")

        print(
            f"\n  总计: {model_errors_per_source * len(SOURCE_IDS) + tool_errors_per_source * len(SOURCE_IDS)} 条",
        )

    except Exception as e:
        print(f"插入失败: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
