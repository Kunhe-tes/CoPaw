# -*- coding: utf-8 -*-
"""插入运营看板测试数据.

用于测试 BusinessOverview 页面的各项统计功能。

运行方式:
    cd monitor
    .venv/Scripts/python scripts/insert_tracing_test_data.py
"""

import asyncio
import json
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 添加 src 目录到 Python 路径
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def load_db_config_from_env_file() -> dict[str, Any]:
    """从环境配置文件加载数据库配置."""
    # 尝试加载 prd.json
    env_file = src_path / "monitor" / "config" / "envs" / "prd.json"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            env_config = json.load(f)
            return {
                "host": env_config.get("MONITOR_DB_HOST", "localhost"),
                "port": int(env_config.get("MONITOR_DB_PORT", 3306)),
                "user": env_config.get("MONITOR_DB_USER", "root"),
                "password": env_config.get("MONITOR_DB_ACCESS", ""),
                "database": env_config.get("MONITOR_DB_NAME", "monitor"),
            }
    return {}


from monitor.app.database.config import MonitorDatabaseConfig
from monitor.app.database.connection import DatabaseConnection

# 测试数据配置
BBK_IDS = [
    "100",
    "200",
    "201",
    "202",
    "203",
    "V00",
]  # 总行、北京、上海、深圳、广州、V00（将并入总行）
BBK_NAMES = {
    "100": "总行",
    "200": "北京分行",
    "201": "上海分行",
    "202": "深圳分行",
    "203": "广州分行",
    "V00": "V00",
}

SOURCE_IDS = ["SZLS", "CMSJY", "UPPCLAW", "copilotClaw", "ruice"]

SKILLS = [
    "智能客服",
    "数据分析助手",
    "文档生成",
    "代码解释",
    "报表查询",
    "风险预警",
    "营销推荐",
    "合规检查",
]

TOOLS = [
    "sql_query",
    "file_read",
    "python_executor",
    "web_search",
    "chart_generator",
    "report_builder",
    "data_validator",
    "notification_sender",
]

MCP_SERVERS = [
    "mysql_server",
    "redis_server",
    "elasticsearch_server",
    "kafka_server",
]

MODELS = ["gpt-4", "claude-3", "glm-4", "qwen-2"]

# 用户池 - 混合真实用户和需要过滤的用户
REAL_USERS = [
    ("zhangsan", "张三"),
    ("lisi", "李四"),
    ("wangwu", "王五"),
    ("zhaoliu", "赵六"),
    ("qianqi", "钱七"),
    ("sunba", "孙八"),
    ("zhoujiu", "周九"),
    ("wushi", "吴十"),
    ("zhengyi", "郑一"),
    ("chenming", "陈明"),
    ("xiaohong", "小红"),
    ("dawei", "大伟"),
    ("xiaoli", "小李"),
    ("meimei", "美美"),
    ("gangqiang", "刚强"),
]

# 需要被过滤的用户（80开头或IT开头）
FILTERED_USERS = [
    ("80user001", "测试用户1"),
    ("80user002", "测试用户2"),
    ("ITadmin", "IT管理员"),
    ("ITtest", "IT测试员"),
]

CHANNELS = ["console", "api", "webhook", "mobile"]

STATUS_OPTIONS = ["completed", "error", "cancelled"]


def random_datetime(
    start: datetime,
    end: datetime,
) -> datetime:
    """生成随机时间."""
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=random_seconds)


def generate_trace(
    start_time: datetime,
    source_id: str,
    user_id: str,
    user_name: str,
    bbk_id: str,
) -> dict[str, Any]:
    """生成一条 trace 记录."""
    trace_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    # 随机决定是否使用技能
    use_skills = random.random() > 0.3
    skills_used = (
        random.sample(SKILLS, random.randint(1, 3)) if use_skills else []
    )
    tools_used = (
        random.sample(TOOLS, random.randint(0, 4)) if use_skills else []
    )

    # 模型使用
    model_name = random.choice(MODELS)
    input_tokens = random.randint(100, 5000)
    output_tokens = random.randint(50, 2000)
    total_tokens = input_tokens + output_tokens

    # 时长
    duration_ms = random.randint(500, 30000)

    # 状态
    status = random.choices(
        STATUS_OPTIONS,
        weights=[0.85, 0.1, 0.05],  # 85%成功, 10%失败, 5%取消
    )[0]

    end_time = start_time + timedelta(milliseconds=duration_ms)

    # 用户消息
    user_messages = [
        "帮我分析一下这个月的销售数据",
        "查询客户投诉统计",
        "生成周报",
        "检查合规风险",
        "推荐营销方案",
        "解释这段代码",
        "生成数据可视化图表",
        "查询数据库中的异常记录",
    ]
    user_message = random.choice(user_messages)

    return {
        "trace_id": trace_id,
        "source_id": source_id,
        "user_id": user_id,
        "user_name": user_name,
        "bbk_id": bbk_id,
        "session_id": session_id,
        "session_name": user_message[:50],
        "channel": random.choice(CHANNELS),
        "start_time": start_time,
        "end_time": end_time,
        "duration_ms": duration_ms,
        "model_name": model_name,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "tools_used": tools_used,
        "skills_used": skills_used,
        "status": status,
        "error": "模拟错误信息" if status == "error" else None,
        "user_message": user_message,
    }


def generate_span(
    trace: dict[str, Any],
    event_type: str,
    start_offset_ms: int,
) -> dict[str, Any]:
    """生成一条 span 记录."""
    span_id = str(uuid.uuid4())
    span_start = trace["start_time"] + timedelta(milliseconds=start_offset_ms)

    # 根据事件类型设置不同字段
    span_data = {
        "span_id": span_id,
        "trace_id": trace["trace_id"],
        "source_id": trace["source_id"],
        "user_id": trace["user_id"],
        "user_name": trace["user_name"],
        "bbk_id": trace["bbk_id"],
        "session_id": trace["session_id"],
        "channel": trace["channel"],
        "event_type": event_type,
        "start_time": span_start,
    }

    if event_type == "llm_input":
        span_data["model_name"] = trace["model_name"]
        span_data["input_tokens"] = trace["total_input_tokens"]
        span_data["duration_ms"] = None
        span_data["end_time"] = None

    elif event_type == "llm_output":
        span_data["model_name"] = trace["model_name"]
        span_data["output_tokens"] = trace["total_output_tokens"]
        span_data["duration_ms"] = random.randint(100, 5000)
        span_data["end_time"] = span_start + timedelta(
            milliseconds=span_data["duration_ms"],
        )

    elif event_type == "skill_invocation":
        span_data["skill_name"] = random.choice(SKILLS)
        span_data["duration_ms"] = random.randint(200, 3000)
        span_data["end_time"] = span_start + timedelta(
            milliseconds=span_data["duration_ms"],
        )

    elif event_type in ["tool_call_start", "tool_call_end"]:
        span_data["tool_name"] = random.choice(TOOLS)
        # MCP 工具
        if random.random() > 0.7:
            span_data["mcp_server"] = random.choice(MCP_SERVERS)
        span_data["duration_ms"] = random.randint(50, 1000)
        span_data["end_time"] = span_start + timedelta(
            milliseconds=span_data["duration_ms"],
        )
        span_data["name"] = f"{span_data['tool_name']} execution"

    return span_data


async def insert_test_data(
    db: DatabaseConnection,
    hours_back: int = 24,
    traces_per_hour: int = 50,
) -> tuple[int, int]:
    """插入测试数据.

    Args:
        db: 数据库连接
        hours_back: 回溯多少小时（默认24小时，覆盖今天）
        traces_per_hour: 每小时生成多少条 trace

    Returns:
        (插入的 trace 数量, 插入的 span 数量)
    """
    now = datetime.now()
    start_time = now - timedelta(hours=hours_back)

    trace_count = 0
    span_count = 0

    # 为每个小时生成数据
    for hour_offset in range(hours_back):
        hour_start = start_time + timedelta(hours=hour_offset)
        hour_end = hour_start + timedelta(hours=1)

        # 每小时生成 traces_per_hour 条记录
        for _ in range(traces_per_hour):
            # 随机选择用户和分行
            # 70%真实用户, 30%过滤用户
            if random.random() > 0.3:
                user_id, user_name = random.choice(REAL_USERS)
            else:
                user_id, user_name = random.choice(FILTERED_USERS)

            bbk_id = random.choice(BBK_IDS)
            source_id = random.choice(SOURCE_IDS)

            # 随机时间点
            trace_start = random_datetime(hour_start, hour_end)

            # 生成 trace
            trace = generate_trace(
                trace_start,
                source_id,
                user_id,
                user_name,
                bbk_id,
            )

            # 插入 trace
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
            trace_params = (
                trace["trace_id"],
                trace["source_id"],
                trace["user_id"],
                trace["user_name"],
                trace["bbk_id"],
                trace["session_id"],
                trace["session_name"],
                trace["channel"],
                trace["start_time"],
                trace["end_time"],
                trace["duration_ms"],
                trace["model_name"],
                trace["total_input_tokens"],
                trace["total_output_tokens"],
                trace["total_tokens"],
                (
                    json.dumps(trace["tools_used"])
                    if trace["tools_used"]
                    else None
                ),
                (
                    json.dumps(trace["skills_used"])
                    if trace["skills_used"]
                    else None
                ),
                trace["status"],
                trace["error"],
                trace["user_message"],
            )

            await db.execute(trace_sql, trace_params)
            trace_count += 1

            # 为每条 trace 生成 spans
            # LLM 输入/输出
            llm_input_span = generate_span(trace, "llm_input", 0)
            llm_output_span = generate_span(
                trace,
                "llm_output",
                trace["duration_ms"] // 2,
            )

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

            # 插入 LLM spans
            for span in [llm_input_span, llm_output_span]:
                span_params = (
                    span["span_id"],
                    span["trace_id"],
                    span["source_id"],
                    span.get("name"),
                    span["event_type"],
                    span["start_time"],
                    span.get("end_time"),
                    span.get("duration_ms"),
                    span["user_id"],
                    span["user_name"],
                    span["bbk_id"],
                    span["session_id"],
                    span["channel"],
                    span.get("model_name"),
                    span.get("input_tokens"),
                    span.get("output_tokens"),
                    span.get("tool_name"),
                    span.get("skill_name"),
                    span.get("mcp_server"),
                    span.get("error"),
                )
                await db.execute(span_sql, span_params)
                span_count += 1

            # 如果有技能调用，生成技能 spans
            for skill_name in trace.get("skills_used", []):
                skill_offset = random.randint(100, trace["duration_ms"] // 3)
                skill_span = generate_span(
                    trace,
                    "skill_invocation",
                    skill_offset,
                )
                skill_span["skill_name"] = skill_name

                span_params = (
                    skill_span["span_id"],
                    skill_span["trace_id"],
                    skill_span["source_id"],
                    skill_span.get("name"),
                    skill_span["event_type"],
                    skill_span["start_time"],
                    skill_span.get("end_time"),
                    skill_span.get("duration_ms"),
                    skill_span["user_id"],
                    skill_span["user_name"],
                    skill_span["bbk_id"],
                    skill_span["session_id"],
                    skill_span["channel"],
                    skill_span.get("model_name"),
                    skill_span.get("input_tokens"),
                    skill_span.get("output_tokens"),
                    skill_span.get("tool_name"),
                    skill_span["skill_name"],
                    skill_span.get("mcp_server"),
                    skill_span.get("error"),
                )
                await db.execute(span_sql, span_params)
                span_count += 1

            # 如果有工具调用，生成工具 spans
            for tool_name in trace.get("tools_used", []):
                tool_offset = random.randint(200, trace["duration_ms"] // 2)
                tool_span = generate_span(
                    trace,
                    "tool_call_start",
                    tool_offset,
                )
                tool_span["tool_name"] = tool_name

                span_params = (
                    tool_span["span_id"],
                    tool_span["trace_id"],
                    tool_span["source_id"],
                    tool_span.get("name"),
                    tool_span["event_type"],
                    tool_span["start_time"],
                    tool_span.get("end_time"),
                    tool_span.get("duration_ms"),
                    tool_span["user_id"],
                    tool_span["user_name"],
                    tool_span["bbk_id"],
                    tool_span["session_id"],
                    tool_span["channel"],
                    tool_span.get("model_name"),
                    tool_span.get("input_tokens"),
                    tool_span.get("output_tokens"),
                    tool_span["tool_name"],
                    tool_span.get("skill_name"),
                    tool_span.get("mcp_server"),
                    tool_span.get("error"),
                )
                await db.execute(span_sql, span_params)
                span_count += 1

    return trace_count, span_count


async def main():
    """主函数."""
    print("=" * 60)
    print("运营看板测试数据插入脚本")
    print("=" * 60)

    # 从配置文件加载数据库配置
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
    print(f"数据库配置: {config.host}:{config.port}/{config.database}")

    # 创建连接
    db = DatabaseConnection(config)
    await db.connect()
    print("数据库连接成功")

    # 插入数据
    print("\n开始插入测试数据...")
    print("配置: 24小时数据, 每小时50条记录")

    trace_count, span_count = await insert_test_data(
        db,
        hours_back=24,
        traces_per_hour=50,
    )

    print("\n插入完成:")
    print(f"  - Trace 记录: {trace_count} 条")
    print(f"  - Span 记录: {span_count} 条")

    # 关闭连接
    await db.close()
    print("数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())
