# -*- coding: utf-8 -*-
"""生成报错详情弹窗的测试数据。

覆盖场景：
1. 多轮会话消息 - 同一个 session 下有多条 trace
2. 各种报错类型：模型报错(llm_input)、工具报错(tool_call_end)
3. 报错消息不同长度：短(<20)、中(50-100)、长(>200)
4. session_name 不同情况：有/无、长/短

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_error_detail_test_data.py
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
MODELS = ["gpt-4o", "claude-3-5-sonnet", "glm-4", "qwen-2.5"]
CHANNELS = ["console", "api", "webhook", "mobile"]

REAL_USERS = [
    ("zhangsan", "张三"),
    ("lisi", "李四"),
    ("wangwu", "王五"),
    ("zhaoliu", "赵六"),
    ("xiaohong", "小红"),
    ("dawei", "大伟"),
]

SKILLS = ["数据分析助手", "智能客服", "文档生成", "报表查询"]
TOOLS = [
    "sql_query",
    "python_executor",
    "web_search",
    "file_read",
    "chart_generator",
]

# 报错消息模板 - 不同长度
SHORT_ERRORS = [
    "timeout",
    "连接失败",
    "内存不足",
    "参数错误",
]

MEDIUM_ERRORS = [
    "Connection timeout: Failed to connect to model endpoint after 30s",
    "Database connection refused: Access denied for user 'admin'",
    "Python execution error: NameError name 'df' is not defined",
    "Model service unavailable: HTTP 503 Service Temporarily Unavailable",
    "Rate limit exceeded: Too many requests in 1 minute window",
    "Tool execution failed: Invalid SQL syntax near SELECT",
]

LONG_ERRORS = [
    "Connection timeout after 30000ms: Failed to establish connection to model provider endpoint at https://api.example.com/v1/chat/completions. The server may be temporarily unavailable or experiencing high load. Please try again later or contact support if the issue persists.",
    "Database query execution failed with error code 0x8001: The query execution plan exceeded the maximum allowed complexity threshold. Query involved 15 table joins with nested subqueries exceeding 3 levels. Consider simplifying the query or breaking it into multiple smaller queries.",
    "Python runtime error during tool execution: Traceback (most recent call last): File '/app/tools/analyzer.py', line 142, in process_data result = transform_dataframe(input_data) KeyError: 'column_name' The specified column does not exist in the input dataframe structure.",
    "Model API authentication failure: The provided API key has been revoked or expired. Error code: AUTH_KEY_REVOKED. Please regenerate a new API key from the provider dashboard and update your configuration settings accordingly.",
]

# 多轮会话的用户消息模板
USER_MESSAGES_MULTI_ROUND = [
    # 第一轮：简单请求
    [
        "帮我查询上个月的存款数据",
    ],
    # 第二轮：追加分析
    [
        "帮我查询上个月的存款数据",
        "按分行分组统计一下",
    ],
    # 第三轮：复杂多轮
    [
        "分析一下最近一个月北京分行的存款趋势",
        "重点关注活期存款和定期存款的比例变化",
        "帮我生成一份可视化的分析报告",
    ],
    # 四轮深度对话
    [
        "查询客户投诉数据",
        "统计各分行的投诉数量",
        "分析投诉的主要原因",
        "生成改进建议报告",
    ],
]

# session_name 模板
SESSION_NAMES = [
    "存款数据分析",
    "客户投诉统计查询",
    "月度报表生成任务",
    "风险预警监控",
    "这是一个很长的会话名称用于测试截断显示效果超过一百字符的情况",
]


async def main():
    """生成报错详情测试数据."""
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
            "DELETE FROM swe_tracing_spans WHERE user_id LIKE 'test-detail%'",
        )
        await db.execute(
            "DELETE FROM swe_tracing_traces WHERE user_id LIKE 'test-detail%'",
        )
        print("已清理旧测试数据\n")

        now = datetime.now()
        start_time = now - timedelta(days=3)

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

        span_sql = """
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

        trace_count = 0
        span_count = 0
        session_count = 0

        # === 场景1: 多轮会话（同一个 session 多条 trace）===
        print("=== 场景1: 多轮会话消息 ===")
        for i, messages in enumerate(USER_MESSAGES_MULTI_ROUND):
            session_id = str(uuid.uuid4())
            user_id, user_name = random.choice(REAL_USERS)
            bbk_id = random.choice(BBK_IDS)
            source_id = random.choice(SOURCE_IDS)
            session_name = random.choice(SESSION_NAMES[:4])  # 短 session_name

            print(f"\n会话 {i + 1}: {session_name} ({len(messages)} 轮对话)")

            for j, user_message in enumerate(messages):
                trace_id = str(uuid.uuid4())
                trace_start = start_time + timedelta(
                    days=random.randint(0, 2),
                    hours=random.randint(0, 23),
                    minutes=j * 5,  # 每轮间隔5分钟
                )
                duration = random.randint(2000, 15000)
                trace_end = trace_start + timedelta(milliseconds=duration)

                model_name = random.choice(MODELS)
                input_tokens = random.randint(200, 3000)
                output_tokens = random.randint(100, 1500)

                # 最后一条对话有报错（模拟在多轮对话中出现错误）
                if j == len(messages) - 1:
                    status = "error"
                    error_msg = random.choice(MEDIUM_ERRORS)
                    error_type = random.choice(["llm_input", "tool_call_end"])
                else:
                    status = "completed"
                    error_msg = None
                    error_type = None

                skills_used = random.sample(SKILLS, random.randint(1, 2))
                tools_used = random.sample(TOOLS, random.randint(0, 2))

                trace_params = (
                    trace_id,
                    source_id,
                    f"test-detail-{user_id}",
                    user_name,
                    bbk_id,
                    session_id,
                    session_name,
                    random.choice(CHANNELS),
                    trace_start,
                    trace_end,
                    duration,
                    model_name,
                    input_tokens,
                    output_tokens,
                    input_tokens + output_tokens,
                    json.dumps(tools_used),
                    json.dumps(skills_used),
                    status,
                    error_msg,
                    user_message,
                )

                await db.execute(trace_sql, trace_params)
                trace_count += 1

                # 生成 spans
                # llm_input span
                llm_input_span_id = str(uuid.uuid4())
                llm_input_error = (
                    error_msg if error_type == "llm_input" else None
                )
                await db.execute(
                    span_sql,
                    (
                        llm_input_span_id,
                        trace_id,
                        source_id,
                        f"{model_name} call",
                        "llm_input",
                        trace_start,
                        None,
                        None,
                        f"test-detail-{user_id}",
                        user_name,
                        bbk_id,
                        session_id,
                        random.choice(CHANNELS),
                        model_name,
                        input_tokens,
                        None,
                        None,
                        None,
                        None,
                        llm_input_error,
                    ),
                )
                span_count += 1

                # 如果有工具调用，生成 tool_call_end spans
                for tool_name in tools_used:
                    tool_span_id = str(uuid.uuid4())
                    tool_error = (
                        error_msg
                        if error_type == "tool_call_end" and error_msg
                        else None
                    )
                    tool_start = trace_start + timedelta(
                        milliseconds=random.randint(500, duration - 500),
                    )
                    tool_duration = random.randint(100, 2000)

                    await db.execute(
                        span_sql,
                        (
                            tool_span_id,
                            trace_id,
                            source_id,
                            f"{tool_name} execution",
                            "tool_call_end",
                            tool_start,
                            tool_start + timedelta(milliseconds=tool_duration),
                            tool_duration,
                            f"test-detail-{user_id}",
                            user_name,
                            bbk_id,
                            session_id,
                            random.choice(CHANNELS),
                            None,
                            None,
                            None,
                            tool_name,
                            None,
                            None,
                            tool_error,
                        ),
                    )
                    span_count += 1

                # llm_output span
                llm_output_span_id = str(uuid.uuid4())
                llm_output_start = trace_start + timedelta(
                    milliseconds=duration // 2,
                )
                await db.execute(
                    span_sql,
                    (
                        llm_output_span_id,
                        trace_id,
                        source_id,
                        f"{model_name} response",
                        "llm_output",
                        llm_output_start,
                        trace_end,
                        duration // 2,
                        f"test-detail-{user_id}",
                        user_name,
                        bbk_id,
                        session_id,
                        random.choice(CHANNELS),
                        model_name,
                        None,
                        output_tokens,
                        None,
                        None,
                        None,
                        None,
                    ),
                )
                span_count += 1

                print(
                    f"  第{j + 1}轮: {user_message[:30]}... | 状态: {status}"
                )

            session_count += 1

        # === 场景2: 报错消息不同长度 ===
        print("\n=== 场景2: 报错消息不同长度 ===")

        error_scenarios = [
            ("短报错", SHORT_ERRORS),
            ("中等报错", MEDIUM_ERRORS),
            ("长报错", LONG_ERRORS),
        ]

        for scenario_name, errors in error_scenarios:
            print(f"\n{scenario_name} ({len(errors)} 种):")

            for error_msg in errors:
                session_id = str(uuid.uuid4())
                trace_id = str(uuid.uuid4())
                user_id, user_name = random.choice(REAL_USERS)
                bbk_id = random.choice(BBK_IDS)
                source_id = random.choice(SOURCE_IDS)

                trace_start = start_time + timedelta(
                    days=random.randint(0, 2),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )
                duration = random.randint(1000, 10000)
                trace_end = trace_start + timedelta(milliseconds=duration)

                model_name = random.choice(MODELS)
                input_tokens = random.randint(100, 2000)
                output_tokens = random.randint(50, 1000)

                # 随机选择报错类型
                error_type = random.choice(["llm_input", "tool_call_end"])

                trace_params = (
                    trace_id,
                    source_id,
                    f"test-detail-{user_id}",
                    user_name,
                    bbk_id,
                    session_id,
                    f"测试{scenario_name}",
                    random.choice(CHANNELS),
                    trace_start,
                    trace_end,
                    duration,
                    model_name,
                    input_tokens,
                    output_tokens,
                    input_tokens + output_tokens,
                    json.dumps([]),
                    json.dumps([]),
                    "error",
                    error_msg,
                    "测试报错场景",
                )

                await db.execute(trace_sql, trace_params)
                trace_count += 1

                # 生成带报错的 span
                span_id = str(uuid.uuid4())
                await db.execute(
                    span_sql,
                    (
                        span_id,
                        trace_id,
                        source_id,
                        "error span",
                        error_type,
                        trace_start,
                        trace_end,
                        duration,
                        f"test-detail-{user_id}",
                        user_name,
                        bbk_id,
                        session_id,
                        random.choice(CHANNELS),
                        model_name if error_type == "llm_input" else None,
                        input_tokens if error_type == "llm_input" else None,
                        None,
                        "test_tool" if error_type == "tool_call_end" else None,
                        None,
                        None,
                        error_msg,
                    ),
                )
                span_count += 1

                print(
                    f"  - {error_msg[:50]}{'...' if len(error_msg) > 50 else ''}",
                )

        # === 场景3: session_name 不同情况 ===
        print("\n=== 场景3: session_name 不同情况 ===")

        # 无 session_name
        print("\n无 session_name (显示 session_id):")
        for i in range(3):
            session_id = str(uuid.uuid4())
            trace_id = str(uuid.uuid4())
            user_id, user_name = random.choice(REAL_USERS)
            bbk_id = random.choice(BBK_IDS)
            source_id = random.choice(SOURCE_IDS)

            trace_start = start_time + timedelta(hours=i * 2)
            duration = random.randint(2000, 8000)
            error_msg = random.choice(MEDIUM_ERRORS)
            error_type = "llm_input"

            trace_params = (
                trace_id,
                source_id,
                f"test-detail-{user_id}",
                user_name,
                bbk_id,
                session_id,
                None,  # 无 session_name
                random.choice(CHANNELS),
                trace_start,
                trace_start + timedelta(milliseconds=duration),
                duration,
                random.choice(MODELS),
                random.randint(200, 2000),
                random.randint(100, 1000),
                random.randint(300, 3000),
                json.dumps([]),
                json.dumps([]),
                "error",
                error_msg,
                "无session_name测试",
            )

            await db.execute(trace_sql, trace_params)
            trace_count += 1

            # 生成报错 span
            span_id = str(uuid.uuid4())
            await db.execute(
                span_sql,
                (
                    span_id,
                    trace_id,
                    source_id,
                    "llm call",
                    error_type,
                    trace_start,
                    trace_start + timedelta(milliseconds=duration),
                    duration,
                    f"test-detail-{user_id}",
                    user_name,
                    bbk_id,
                    session_id,
                    random.choice(CHANNELS),
                    random.choice(MODELS),
                    random.randint(200, 2000),
                    None,
                    None,
                    None,
                    None,
                    error_msg,
                ),
            )
            span_count += 1

            print(f"  {i + 1}. session_id: {session_id[:24]}...")

        # 长 session_name (>100字符)
        print("\n长 session_name (>100字符):")
        long_session_name = SESSION_NAMES[4]  # 超长名称
        session_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        user_id, user_name = random.choice(REAL_USERS)
        bbk_id = random.choice(BBK_IDS)
        source_id = random.choice(SOURCE_IDS)

        trace_start = start_time + timedelta(hours=10)
        duration = random.randint(3000, 10000)
        error_msg = random.choice(MEDIUM_ERRORS)

        trace_params = (
            trace_id,
            source_id,
            f"test-detail-{user_id}",
            user_name,
            bbk_id,
            session_id,
            long_session_name,
            random.choice(CHANNELS),
            trace_start,
            trace_start + timedelta(milliseconds=duration),
            duration,
            random.choice(MODELS),
            random.randint(200, 2000),
            random.randint(100, 1000),
            random.randint(300, 3000),
            json.dumps(["sql_query"]),
            json.dumps(["数据分析助手"]),
            "error",
            error_msg,
            "长session_name测试",
        )

        await db.execute(trace_sql, trace_params)
        trace_count += 1

        # 生成 spans
        span_id = str(uuid.uuid4())
        await db.execute(
            span_sql,
            (
                span_id,
                trace_id,
                source_id,
                "llm call with error",
                "llm_input",
                trace_start,
                trace_start + timedelta(milliseconds=duration),
                duration,
                f"test-detail-{user_id}",
                user_name,
                bbk_id,
                session_id,
                random.choice(CHANNELS),
                random.choice(MODELS),
                random.randint(200, 2000),
                None,
                None,
                None,
                None,
                error_msg,
            ),
        )
        span_count += 1

        print(
            f"  session_name: {long_session_name[:50]}... (共{len(long_session_name)}字符)",
        )

        # === 场景4: 模型报错 vs 工具报错 ===
        print("\n=== 场景4: 模型报错 vs 工具报错 ===")

        for error_type in ["llm_input", "tool_call_end"]:
            print(f"\n{error_type} 报错:")

            for i in range(2):
                session_id = str(uuid.uuid4())
                trace_id = str(uuid.uuid4())
                user_id, user_name = random.choice(REAL_USERS)
                bbk_id = random.choice(BBK_IDS)
                source_id = random.choice(SOURCE_IDS)

                trace_start = start_time + timedelta(hours=i * 5)
                duration = random.randint(2000, 10000)
                error_msg = random.choice(MEDIUM_ERRORS)
                model_name = random.choice(MODELS)
                tool_name = (
                    "sql_query" if error_type == "tool_call_end" else None
                )

                trace_params = (
                    trace_id,
                    source_id,
                    f"test-detail-{user_id}",
                    user_name,
                    bbk_id,
                    session_id,
                    f"{error_type}测试{i + 1}",
                    random.choice(CHANNELS),
                    trace_start,
                    trace_start + timedelta(milliseconds=duration),
                    duration,
                    model_name,
                    random.randint(200, 2000),
                    random.randint(100, 1000),
                    random.randint(300, 3000),
                    json.dumps([tool_name] if tool_name else []),
                    json.dumps([]),
                    "error",
                    error_msg,
                    f"测试{error_type}报错",
                )

                await db.execute(trace_sql, trace_params)
                trace_count += 1

                # 生成报错 span
                span_id = str(uuid.uuid4())
                await db.execute(
                    span_sql,
                    (
                        span_id,
                        trace_id,
                        source_id,
                        f"{error_type} error",
                        error_type,
                        trace_start,
                        trace_start + timedelta(milliseconds=duration),
                        duration,
                        f"test-detail-{user_id}",
                        user_name,
                        bbk_id,
                        session_id,
                        random.choice(CHANNELS),
                        model_name if error_type == "llm_input" else None,
                        (
                            random.randint(200, 2000)
                            if error_type == "llm_input"
                            else None
                        ),
                        None,
                        tool_name if error_type == "tool_call_end" else None,
                        None,
                        None,
                        error_msg,
                    ),
                )
                span_count += 1

                label = (
                    "模型报错"
                    if error_type == "llm_input"
                    else f"工具报错({tool_name})"
                )
                print(f"  {i + 1}. {label}: {error_msg[:40]}...")

        print(f"\n{'=' * 60}")
        print("\n数据插入完成:")
        print(f"  - Trace 记录: {trace_count} 条")
        print(f"  - Span 记录: {span_count} 条")
        print(f"  - 会话数量: {session_count + 3 + 1 + 4} 个")

        # 验证数据
        print(f"\n{'=' * 60}")
        print("验证数据:")

        # 查询报错数量
        error_traces = await db.fetch_all("""
            SELECT trace_id, error, session_name
            FROM swe_tracing_traces
            WHERE user_id LIKE 'test-detail%'
              AND status = 'error'
            ORDER BY start_time DESC
            LIMIT 10
        """)
        print("\n报错 trace 数量 (显示前10条):")
        for row in error_traces:
            error_preview = row["error"][:40] if row["error"] else None
            session_name = row["session_name"] or "(无)"
            print(
                f"  - {row['trace_id'][:16]}... | {session_name[:20]}... | {error_preview}...",
            )

        # 查询报错 spans
        error_spans = await db.fetch_all("""
            SELECT span_id, event_type, error
            FROM swe_tracing_spans
            WHERE user_id LIKE 'test-detail%'
              AND error IS NOT NULL
              AND error != ''
            ORDER BY start_time DESC
            LIMIT 10
        """)
        print(f"\n报错 span 数量: {len(error_spans)} 条")
        print("按事件类型统计:")
        llm_errors = [s for s in error_spans if s["event_type"] == "llm_input"]
        tool_errors = [
            s for s in error_spans if s["event_type"] == "tool_call_end"
        ]
        print(f"  - 模型报错 (llm_input): {len(llm_errors)} 条")
        print(f"  - 工具报错 (tool_call_end): {len(tool_errors)} 条")

    except Exception as e:
        print(f"插入失败: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        await db.close()
        print("\n数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())
