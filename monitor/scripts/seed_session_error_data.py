# -*- coding: utf-8 -*-
"""生成报错会话筛选功能的测试数据。

在 swe_tracing_traces 表中插入带有 status='error' 的测试数据，
用于验证 has_error 筛选功能。

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_session_error_data.py
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
    """从用户 envs.json 加载数据库配置."""
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
    return {}


from monitor.app.database.config import MonitorDatabaseConfig
from monitor.app.database.connection import DatabaseConnection

BBK_IDS = ["100", "200", "201", "202", "203", "V00"]
SOURCE_IDS = ["SZLS", "CMSJY", "UPPCLAW", "copilotClaw", "ruice"]
MODELS = ["gpt-4", "claude-3", "glm-4", "qwen-2"]
CHANNELS = ["console", "api", "webhook", "mobile"]

REAL_USERS = [
    ("zhangsan", "张三"),
    ("lisi", "李四"),
    ("wangwu", "王五"),
    ("zhaoliu", "赵六"),
]

SKILLS = ["智能客服", "数据分析助手", "文档生成", "代码解释"]
TOOLS = ["sql_query", "file_read", "python_executor", "web_search"]


async def main():
    """生成报错会话测试数据."""
    db_config = load_db_config_from_env_file()
    if not db_config:
        print("错误: 无法从 ~/.swe.secret/envs.json 加载数据库配置")
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
            "DELETE FROM swe_tracing_traces WHERE user_id LIKE 'test-error-user%'",
        )
        print("已清理旧测试数据\n")

        now = datetime.now()
        start_time = now - timedelta(days=7)

        trace_count = 0
        session_count = 0

        trace_sql = """
            INSERT INTO swe_tracing_traces (
                trace_id, source_id, user_id, user_name, bbk_id,
                session_id, session_name, channel, start_time, end_time,
                duration_ms, model_name, total_input_tokens, total_output_tokens,
                total_tokens, tools_used, skills_used, status, error, user_message
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        # 创建几个会话，部分有报错，部分无报错
        sessions = []
        for i in range(10):
            session_id = str(uuid.uuid4())
            user_id, user_name = random.choice(REAL_USERS)
            bbk_id = random.choice(BBK_IDS)
            source_id = random.choice(SOURCE_IDS)

            # 每个会话有 3-5 条 trace
            num_traces = random.randint(3, 5)
            has_error = i < 5  # 前5个会话有报错，后5个无报错

            sessions.append(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "bbk_id": bbk_id,
                    "source_id": source_id,
                    "num_traces": num_traces,
                    "has_error": has_error,
                },
            )

        for session in sessions:
            session_start = start_time + timedelta(
                seconds=random.randint(
                    0,
                    int((now - start_time).total_seconds()),
                ),
            )

            for j in range(session["num_traces"]):
                trace_id = str(uuid.uuid4())
                trace_start = session_start + timedelta(minutes=j * 5)
                duration = random.randint(500, 30000)
                trace_end = trace_start + timedelta(milliseconds=duration)

                # 会话内有一条报错（如果该会话被标记为有报错）
                if session["has_error"] and j == random.randint(
                    0,
                    session["num_traces"] - 1,
                ):
                    status = "error"
                    error_msg = random.choice(
                        [
                            "Connection timeout to model provider",
                            "Database connection refused",
                            "Python execution error: NameError",
                            "Model service unavailable: 503",
                        ],
                    )
                else:
                    status = "completed"
                    error_msg = None

                user_message = random.choice(
                    [
                        "帮我分析一下这个月的销售数据",
                        "查询客户投诉统计",
                        "生成周报",
                        "检查合规风险",
                    ],
                )

                skills_used = random.sample(SKILLS, random.randint(1, 2))
                tools_used = random.sample(TOOLS, random.randint(0, 2))

                trace_params = (
                    trace_id,
                    session["source_id"],
                    f"test-error-user-{session['user_id']}",
                    session["user_name"],
                    session["bbk_id"],
                    session["session_id"],
                    user_message[:30],
                    random.choice(CHANNELS),
                    trace_start,
                    trace_end,
                    duration,
                    random.choice(MODELS),
                    random.randint(100, 5000),
                    random.randint(50, 2000),
                    random.randint(150, 7000),
                    json.dumps(tools_used),
                    json.dumps(skills_used),
                    status,
                    error_msg,
                    user_message,
                )

                await db.execute(trace_sql, trace_params)
                trace_count += 1

            session_count += 1
            status_label = "有报错" if session["has_error"] else "无报错"
            print(
                f"  会话 {session_count}: {session['session_id'][:8]}... ({status_label}, {session['num_traces']} 条 trace)",
            )

        print(f"\n共插入 {trace_count} 条 trace，{session_count} 个会话")

        # 验证数据
        print("\n=== 验证数据 ===")

        # 查询报错会话数量
        error_sessions = await db.fetch_all("""
            SELECT DISTINCT session_id, COUNT(*) as trace_count
            FROM swe_tracing_traces
            WHERE user_id LIKE 'test-error-user%'
              AND status = 'error'
            GROUP BY session_id
        """)
        print(f"报错会话数量: {len(error_sessions)} 个")

        # 查询所有会话
        all_sessions = await db.fetch_all("""
            SELECT DISTINCT session_id
            FROM swe_tracing_traces
            WHERE user_id LIKE 'test-error-user%'
        """)
        print(f"总会话数量: {len(all_sessions)} 个")

        # 验证筛选逻辑
        print("\n=== 验证 has_error 筛选逻辑 ===")
        has_error_result = await db.fetch_all("""
            SELECT DISTINCT session_id
            FROM swe_tracing_traces
            WHERE user_id LIKE 'test-error-user%'
              AND session_id IN (SELECT DISTINCT session_id FROM swe_tracing_traces WHERE status = 'error')
        """)
        print(f"has_error=True 筛选结果: {len(has_error_result)} 个会话")

        no_error_result = await db.fetch_all("""
            SELECT DISTINCT session_id
            FROM swe_tracing_traces
            WHERE user_id LIKE 'test-error-user%'
              AND session_id NOT IN (SELECT DISTINCT session_id FROM swe_tracing_traces WHERE status = 'error')
        """)
        print(f"has_error=False 筛选结果: {len(no_error_result)} 个会话")

    except Exception as e:
        print(f"插入失败: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
