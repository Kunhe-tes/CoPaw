# -*- coding: utf-8 -*-
"""补充报错详情弹窗的边界场景测试数据。

覆盖场景：
1. Token 边界：0、超大(>100K)
2. 时长边界：0ms、<1s、>1h
3. 无工具调用：纯模型报错
4. 多工具成功后报错：调用链路展示
5. 模型部分响应后报错：有 model_output
6. 用户消息为空：user_message 为 None
7. 无分行信息：bbk_id 为 None
8. 无用户名：只显示 user_id
9. 无模型名：model_name 为 None
10. MCP 工具报错：显示 mcp_server
11. 特殊字符：换行、引号

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_error_edge_cases.py
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

SOURCE_IDS = ["SZLS", "CMSJY", "UPPCLAW", "copilotClaw", "ruice"]
MODELS = ["gpt-4o", "claude-3-5-sonnet", "glm-4", "qwen-2.5", None]
CHANNELS = ["console", "api", "webhook", "mobile"]

MCP_SERVERS = [
    "mysql_server",
    "redis_server",
    "elasticsearch_server",
    "kafka_server",
]

TOOLS = [
    "sql_query",
    "python_executor",
    "web_search",
    "file_read",
    "chart_generator",
]

# 特殊字符报错消息
SPECIAL_CHAR_ERRORS = [
    "错误: 包含换行符\n第二行内容\n第三行内容",
    "错误: 包含引号 'single' 和 \"double\" 引号",
    "错误: 包含HTML标签 <script>alert('test')</script>",
    "错误: 包含特殊符号 @#$%^&*(){}[]|\\",
    "错误: 包含中文引号「」『』【】",
]


async def insert_trace_and_spans(
    db: DatabaseConnection,
    trace_id: str,
    source_id: str,
    user_id: str,
    user_name: str | None,
    bbk_id: str | None,
    session_id: str,
    session_name: str | None,
    channel: str,
    trace_start: datetime,
    duration_ms: int,
    model_name: str | None,
    input_tokens: int,
    output_tokens: int,
    tools_used: list[str],
    skills_used: list[str],
    status: str,
    error: str,
    user_message: str | None,
    model_output: str | None,
    error_type: str,
    tool_name: str | None,
    mcp_server: str | None,
) -> tuple[int, int]:
    """插入一条 trace 和相关 spans."""
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

    total_tokens = input_tokens + output_tokens
    trace_end = trace_start + timedelta(milliseconds=duration_ms)

    trace_params = (
        trace_id,
        source_id,
        user_id,
        user_name,
        bbk_id,
        session_id,
        session_name,
        channel,
        trace_start,
        trace_end,
        duration_ms,
        model_name,
        input_tokens,
        output_tokens,
        total_tokens,
        json.dumps(tools_used) if tools_used else None,
        json.dumps(skills_used) if skills_used else None,
        status,
        error,
        user_message,
    )

    await db.execute(trace_sql, trace_params)

    # 插入 spans
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

    span_count = 0

    # 工具调用 spans (如果有工具)
    tool_offset = 0
    for tool in tools_used:
        tool_span_id = str(uuid.uuid4())
        tool_start = trace_start + timedelta(milliseconds=tool_offset)
        tool_duration = random.randint(100, 2000)
        tool_end = tool_start + timedelta(milliseconds=tool_duration)

        # 如果这是报错的工具
        tool_error = None
        if error_type == "tool_call_end" and tool == tool_name:
            tool_error = error

        await db.execute(
            span_sql,
            (
                tool_span_id,
                trace_id,
                source_id,
                f"{tool} execution",
                "tool_call_end",
                tool_start,
                tool_end,
                tool_duration,
                user_id,
                user_name,
                bbk_id,
                session_id,
                channel,
                None,
                None,
                None,
                tool,
                None,
                mcp_server if tool == tool_name else None,
                tool_error,
            ),
        )
        span_count += 1
        tool_offset += tool_duration + 100

    # llm_input span
    llm_input_span_id = str(uuid.uuid4())
    llm_input_start = trace_start + timedelta(milliseconds=tool_offset)
    llm_input_error = error if error_type == "llm_input" else None

    await db.execute(
        span_sql,
        (
            llm_input_span_id,
            trace_id,
            source_id,
            f"{model_name or 'model'} call" if model_name else "model call",
            "llm_input",
            llm_input_start,
            None,
            None,
            user_id,
            user_name,
            bbk_id,
            session_id,
            channel,
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

    return 1, span_count


async def main():
    """生成边界场景测试数据."""
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
        # 清理旧边界测试数据
        await db.execute(
            "DELETE FROM swe_tracing_spans WHERE user_id LIKE 'test-edge%'",
        )
        await db.execute(
            "DELETE FROM swe_tracing_traces WHERE user_id LIKE 'test-edge%'",
        )
        print("已清理旧边界测试数据\n")

        now = datetime.now()
        start_time = now - timedelta(hours=12)

        total_traces = 0
        total_spans = 0

        # === 场景1: Token 边界 ===
        print("=== 场景1: Token 边界 ===")

        # Token 为 0
        print("\nToken 为 0 (模型调用失败，无输出):")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user1",
            user_name="测试用户1",
            bbk_id="200",
            session_id=session_id,
            session_name="Token为0测试",
            channel="console",
            trace_start=start_time + timedelta(hours=1),
            duration_ms=500,
            model_name="gpt-4o",
            input_tokens=0,
            output_tokens=0,
            tools_used=[],
            skills_used=[],
            status="error",
            error="Model call failed: no response generated",
            user_message="测试请求",
            model_output=None,
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | Input: 0 | Output: 0")

        # Token 超大 (>100K)
        print("\nToken 超大 (>100K):")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user2",
            user_name="测试用户2",
            bbk_id="201",
            session_id=session_id,
            session_name="Token超大测试",
            channel="api",
            trace_start=start_time + timedelta(hours=2),
            duration_ms=300000,  # 5分钟
            model_name="claude-3-5-sonnet",
            input_tokens=150000,  # 150K
            output_tokens=80000,  # 80K
            tools_used=["sql_query", "python_executor"],
            skills_used=["数据分析助手"],
            status="error",
            error="Token limit exceeded: maximum context length reached",
            user_message="处理大量数据请求",
            model_output="部分响应内容被截断...",
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | Input: 150K | Output: 80K")

        # === 场景2: 时长边界 ===
        print("\n=== 场景2: 时长边界 ===")

        # 时长为 0ms
        print("\n时长为 0ms:")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user3",
            user_name="测试用户3",
            bbk_id="202",
            session_id=session_id,
            session_name="时长为0测试",
            channel="webhook",
            trace_start=start_time + timedelta(hours=3),
            duration_ms=0,
            model_name="glm-4",
            input_tokens=100,
            output_tokens=0,
            tools_used=[],
            skills_used=[],
            status="error",
            error="Instant failure: connection rejected immediately",
            user_message="测试",
            model_output=None,
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | Duration: 0ms")

        # 时长极短 (<1s)
        print("\n时长极短 (500ms < 1s):")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user4",
            user_name="测试用户4",
            bbk_id="203",
            session_id=session_id,
            session_name="时长极短测试",
            channel="console",
            trace_start=start_time + timedelta(hours=4),
            duration_ms=500,
            model_name="qwen-2.5",
            input_tokens=200,
            output_tokens=50,
            tools_used=[],
            skills_used=[],
            status="error",
            error="Quick timeout: request timed out in 500ms",
            user_message="快速测试",
            model_output=None,
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | Duration: 500ms")

        # 时长超长 (>1h = 3600000ms)
        print("\n时长超长 (>1小时):")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user5",
            user_name="测试用户5",
            bbk_id="100",
            session_id=session_id,
            session_name="时长超长测试",
            channel="api",
            trace_start=start_time + timedelta(hours=5),
            duration_ms=7200000,  # 2小时 = 120分钟
            model_name="gpt-4o",
            input_tokens=5000,
            output_tokens=3000,
            tools_used=["sql_query", "python_executor", "chart_generator"],
            skills_used=["数据分析助手", "报表查询"],
            status="error",
            error="Long running task failed after 2 hours: memory exhaustion",
            user_message="大规模数据分析任务",
            model_output="分析进行到一半时出错...",
            error_type="tool_call_end",
            tool_name="python_executor",
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | Duration: 7200000ms (2小时)")

        # === 场景3: 无工具调用（纯模型报错）===
        print("\n=== 场景3: 无工具调用（纯模型报错）===")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user6",
            user_name="测试用户6",
            bbk_id="200",
            session_id=session_id,
            session_name="无工具调用测试",
            channel="console",
            trace_start=start_time + timedelta(hours=6),
            duration_ms=30000,
            model_name="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=0,
            tools_used=[],  # 无工具
            skills_used=[],
            status="error",
            error="Model API error: rate limit exceeded",
            user_message="直接对话请求",
            model_output=None,
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | 无工具调用")

        # === 场景4: 多工具成功后报错 ===
        print("\n=== 场景4: 多工具成功后报错（调用链路展示）===")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user7",
            user_name="测试用户7",
            bbk_id="201",
            session_id=session_id,
            session_name="多工具成功后报错",
            channel="api",
            trace_start=start_time + timedelta(hours=7),
            duration_ms=45000,
            model_name="gpt-4o",
            input_tokens=2000,
            output_tokens=500,
            tools_used=[
                "sql_query",
                "python_executor",
                "web_search",
            ],  # 3个工具
            skills_used=["数据分析助手"],
            status="error",
            error="Final aggregation failed after all tools completed",
            user_message="复杂分析任务",
            model_output="前面步骤都成功了，最后汇总时报错",
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(
            f"  Trace ID: {trace_id[:16]}... | 工具: sql_query OK, python_executor OK, web_search OK -> 模型报错",
        )

        # === 场景5: 模型部分响应后报错 ===
        print("\n=== 场景5: 模型部分响应后报错（有 model_output）===")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user8",
            user_name="测试用户8",
            bbk_id="202",
            session_id=session_id,
            session_name="部分响应后报错",
            channel="console",
            trace_start=start_time + timedelta(hours=8),
            duration_ms=20000,
            model_name="glm-4",
            input_tokens=1500,
            output_tokens=800,
            tools_used=["sql_query"],
            skills_used=["智能客服"],
            status="error",
            error="Model output truncated due to token limit",
            user_message="生成长文本报告",
            model_output="这是模型生成的一部分内容，但在继续生成时遇到了token限制问题，导致输出被截断。前面的内容显示正常...",
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | 有 model_output")

        # === 场景6: 用户消息为空 ===
        print("\n=== 场景6: 用户消息为空（user_message = None）===")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user9",
            user_name="测试用户9",
            bbk_id="203",
            session_id=session_id,
            session_name="用户消息为空测试",
            channel="webhook",
            trace_start=start_time + timedelta(hours=9),
            duration_ms=5000,
            model_name="qwen-2.5",
            input_tokens=100,
            output_tokens=0,
            tools_used=[],
            skills_used=[],
            status="error",
            error="Empty request: no user message provided",
            user_message=None,  # 为空
            model_output=None,
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | user_message = None")

        # === 场景7: 无分行信息 ===
        print("\n=== 场景7: 无分行信息（bbk_id = None）===")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user10",
            user_name="测试用户10",
            bbk_id=None,  # 无分行
            session_id=session_id,
            session_name="无分行信息测试",
            channel="api",
            trace_start=start_time + timedelta(hours=10),
            duration_ms=8000,
            model_name="gpt-4o",
            input_tokens=500,
            output_tokens=200,
            tools_used=["web_search"],
            skills_used=["智能客服"],
            status="error",
            error="Web search failed: timeout",
            user_message="查询外部数据",
            model_output=None,
            error_type="tool_call_end",
            tool_name="web_search",
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | bbk_id = None")

        # === 场景8: 无用户名 ===
        print("\n=== 场景8: 无用户名（只显示 user_id）===")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-anonymous",
            user_name=None,  # 无用户名
            bbk_id="100",
            session_id=session_id,
            session_name="无用户名测试",
            channel="mobile",
            trace_start=start_time + timedelta(hours=11),
            duration_ms=3000,
            model_name="claude-3-5-sonnet",
            input_tokens=300,
            output_tokens=0,
            tools_used=[],
            skills_used=[],
            status="error",
            error="Anonymous user request failed",
            user_message="匿名测试",
            model_output=None,
            error_type="llm_input",
            tool_name=None,
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(
            f"  Trace ID: {trace_id[:16]}... | user_name = None, user_id: test-edge-anonymous",
        )

        # === 场景9: 无模型名 ===
        print("\n=== 场景9: 无模型名（model_name = None）===")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user11",
            user_name="测试用户11",
            bbk_id="V00",
            session_id=session_id,
            session_name="无模型名测试",
            channel="console",
            trace_start=start_time + timedelta(hours=12),
            duration_ms=2000,
            model_name=None,  # 无模型名
            input_tokens=100,
            output_tokens=0,
            tools_used=["python_executor"],
            skills_used=[],
            status="error",
            error="Tool execution failed without model context",
            user_message="工具直接调用",
            model_output=None,
            error_type="tool_call_end",
            tool_name="python_executor",
            mcp_server=None,
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | model_name = None")

        # === 场景10: MCP 工具报错 ===
        print("\n=== 场景10: MCP 工具报错（显示 mcp_server）===")
        trace_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        t, s = await insert_trace_and_spans(
            db=db,
            trace_id=trace_id,
            source_id=random.choice(SOURCE_IDS),
            user_id="test-edge-user12",
            user_name="测试用户12",
            bbk_id="200",
            session_id=session_id,
            session_name="MCP工具报错测试",
            channel="api",
            trace_start=start_time + timedelta(hours=13),
            duration_ms=15000,
            model_name="gpt-4o",
            input_tokens=800,
            output_tokens=400,
            tools_used=["mysql_query"],
            skills_used=["数据分析助手"],
            status="error",
            error="MCP server connection failed: mysql_server unreachable",
            user_message="通过MCP查询数据",
            model_output=None,
            error_type="tool_call_end",
            tool_name="mysql_query",
            mcp_server="mysql_server",  # MCP 服务器名
        )
        total_traces += t
        total_spans += s
        print(f"  Trace ID: {trace_id[:16]}... | mcp_server: mysql_server")

        # === 场景11: 特殊字符报错 ===
        print("\n=== 场景11: 特殊字符报错（换行、引号、HTML）===")
        for i, special_error in enumerate(SPECIAL_CHAR_ERRORS):
            trace_id = str(uuid.uuid4())
            session_id = str(uuid.uuid4())
            t, s = await insert_trace_and_spans(
                db=db,
                trace_id=trace_id,
                source_id=random.choice(SOURCE_IDS),
                user_id=f"test-edge-special{i}",
                user_name=f"特殊字符测试{i + 1}",
                bbk_id="201",
                session_id=session_id,
                session_name=f"特殊字符测试{i + 1}",
                channel="console",
                trace_start=start_time + timedelta(hours=14 + i),
                duration_ms=5000,
                model_name="glm-4",
                input_tokens=200,
                output_tokens=0,
                tools_used=[],
                skills_used=[],
                status="error",
                error=special_error,
                user_message="测试特殊字符",
                model_output=None,
                error_type="llm_input",
                tool_name=None,
                mcp_server=None,
            )
            total_traces += t
            total_spans += s
            preview = (
                special_error[:40] + "..."
                if len(special_error) > 40
                else special_error
            )
            print(f"  {i + 1}. {preview}")

        print(f"\n{'=' * 60}")
        print("\n边界场景数据插入完成:")
        print(f"  - Trace 记录: {total_traces} 条")
        print(f"  - Span 记录: {total_spans} 条")

        # 验证数据
        print(f"\n{'=' * 60}")
        print("验证数据:")

        # 查询各场景统计
        edge_traces = await db.fetch_all("""
            SELECT
                user_id,
                user_name,
                session_name,
                duration_ms,
                total_input_tokens,
                total_output_tokens,
                model_name,
                bbk_id,
                user_message,
                error
            FROM swe_tracing_traces
            WHERE user_id LIKE 'test-edge%'
            ORDER BY start_time
        """)

        print(f"\n共 {len(edge_traces)} 条边界测试记录:")
        print("\n场景分布:")
        token_zero = [t for t in edge_traces if t["total_input_tokens"] == 0]
        token_large = [
            t for t in edge_traces if t["total_input_tokens"] > 100000
        ]
        duration_zero = [t for t in edge_traces if t["duration_ms"] == 0]
        duration_long = [t for t in edge_traces if t["duration_ms"] > 3600000]
        no_bbk = [t for t in edge_traces if t["bbk_id"] is None]
        no_user_name = [t for t in edge_traces if t["user_name"] is None]
        no_model = [t for t in edge_traces if t["model_name"] is None]
        no_user_msg = [t for t in edge_traces if t["user_message"] is None]

        print(f"  - Token 为 0: {len(token_zero)} 条")
        print(f"  - Token 超大 (>100K): {len(token_large)} 条")
        print(f"  - 时长为 0ms: {len(duration_zero)} 条")
        print(f"  - 时长超长 (>1h): {len(duration_long)} 条")
        print(f"  - 无分行信息: {len(no_bbk)} 条")
        print(f"  - 无用户名: {len(no_user_name)} 条")
        print(f"  - 无模型名: {len(no_model)} 条")
        print(f"  - 无用户消息: {len(no_user_msg)} 条")

        # 查询 MCP 报错
        mcp_errors = await db.fetch_all("""
            SELECT span_id, tool_name, mcp_server, error
            FROM swe_tracing_spans
            WHERE user_id LIKE 'test-edge%'
              AND mcp_server IS NOT NULL
              AND error IS NOT NULL
        """)
        print(f"  - MCP 工具报错: {len(mcp_errors)} 条")

        # 查询特殊字符报错
        special_errors = await db.fetch_all("""
            SELECT trace_id, error
            FROM swe_tracing_traces
            WHERE user_id LIKE 'test-edge-special%'
              AND error IS NOT NULL
        """)
        print(f"  - 特殊字符报错: {len(special_errors)} 条")

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
