# -*- coding: utf-8 -*-
"""多轮对话测试数据脚本.

在同一个 session_id 下创建多个 Trace，模拟真实的多轮对话场景。
最后一轮报错，用于测试报错详情弹窗的多轮对话展示。

运行方式:
    cd D:/workspace/CoPaw
    .venv/Scripts/python.exe monitor/scripts/seed_multi_round_conversations.py
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

# 数据源 ID（使用前端 header 匹配的 source_id）
SOURCE_IDS = ["UPPCLAW"]

# 多轮对话场景配置
MULTI_ROUND_SCENARIOS = [
    {
        "name": "数据分析助手 - 多轮纯对话后报错",
        "session_name": "销售数据分析咨询",
        "user_id": "multi-user-1",
        "user_name": "张三",
        "bbk_id": "100",
        "channel": "console",
        "rounds": [
            {
                "user_message": "帮我分析一下上个月的销售数据",
                "model_output": "好的，我来帮您分析上个月的销售数据。根据数据库中的记录，上个月（2024年5月）的销售总额为1250万元，环比增长8.5%。主要销售品类中，电子产品占比最高，达到35%。您还需要了解哪些具体信息？",
                "model_name": "gpt-4o",
                "input_tokens": 50,
                "output_tokens": 120,
                "duration_ms": 3000,
                "tools_used": [],
                "status": "completed",
            },
            {
                "user_message": "电子产品中哪个品牌卖得最好？",
                "model_output": "根据数据分析，电子产品中销售最好的品牌是华为，占比约28%，其次是苹果（22%）和小米（18%）。华为的Mate系列手机是主要贡献品类。",
                "model_name": "gpt-4o",
                "input_tokens": 80,
                "output_tokens": 100,
                "duration_ms": 2500,
                "tools_used": [],
                "status": "completed",
            },
            {
                "user_message": "能帮我生成一个详细的销售报表吗？",
                "model_output": None,  # 报错轮次
                "model_name": "gpt-4o",
                "input_tokens": 100,
                "output_tokens": 0,
                "duration_ms": 5000,
                "tools_used": ["sql_query", "report_generator"],
                "status": "error",
                "error": "Report generation failed: template rendering error",
                "error_type": "tool_call_end",
                "tool_name": "report_generator",
            },
        ],
    },
    {
        "name": "智能客服 - 工具调用对话后报错",
        "session_name": "客户账户问题咨询",
        "user_id": "multi-user-2",
        "user_name": "李四",
        "bbk_id": "200",
        "channel": "api",
        "rounds": [
            {
                "user_message": "我想查询我的账户余额",
                "model_output": "好的，我来帮您查询账户余额。请稍等...",
                "model_name": "glm-4",
                "input_tokens": 30,
                "output_tokens": 40,
                "duration_ms": 2000,
                "tools_used": ["account_query"],
                "status": "completed",
            },
            {
                "user_message": "余额显示正确，但我最近有一笔交易记录不对，能帮我查一下吗？",
                "model_output": "我来帮您查询最近的交易记录。根据系统显示，您最近一周有5笔交易，其中周三有一笔500元的消费记录，是在某电商平台支付。您觉得哪笔记录有问题？",
                "model_name": "glm-4",
                "input_tokens": 80,
                "output_tokens": 150,
                "duration_ms": 4000,
                "tools_used": ["transaction_query"],
                "status": "completed",
            },
            {
                "user_message": "周三那笔500元的消费我没有进行，可能是盗刷",
                "model_output": None,  # 报错轮次
                "model_name": "glm-4",
                "input_tokens": 100,
                "output_tokens": 0,
                "duration_ms": 3000,
                "tools_used": ["fraud_check", "alert_send"],
                "status": "error",
                "error": "Fraud check service unavailable: connection timeout",
                "error_type": "tool_call_end",
                "tool_name": "fraud_check",
            },
        ],
    },
    {
        "name": "代码助手 - 多工具调用后模型报错",
        "session_name": "Python代码生成与调试",
        "user_id": "multi-user-3",
        "user_name": "王五",
        "bbk_id": "300",
        "channel": "webhook",
        "rounds": [
            {
                "user_message": "帮我写一个Python脚本，从数据库读取数据并生成CSV文件",
                "model_output": "好的，我来帮您编写这个脚本。以下是代码框架：\n```python\nimport pandas as pd\nimport sqlite3\n\nconn = sqlite3.connect('data.db')\ndf = pd.read_sql('SELECT * FROM sales', conn)\ndf.to_csv('output.csv', index=False)\n```\n这个脚本会从SQLite数据库读取sales表并导出为CSV。",
                "model_name": "claude-3.5-sonnet",
                "input_tokens": 60,
                "output_tokens": 200,
                "duration_ms": 5000,
                "tools_used": [],
                "status": "completed",
            },
            {
                "user_message": "脚本运行报错了，错误是 sqlite3.OperationalError: no such table: sales",
                "model_output": "抱歉，看起来数据库中没有sales表。让我帮您查询一下数据库中有哪些表。",
                "model_name": "claude-3.5-sonnet",
                "input_tokens": 100,
                "output_tokens": 50,
                "duration_ms": 2000,
                "tools_used": ["python_executor"],
                "status": "completed",
            },
            {
                "user_message": "有products和orders两个表，帮我改成从orders读取",
                "model_output": None,  # 报错轮次
                "model_name": "claude-3.5-sonnet",
                "input_tokens": 80,
                "output_tokens": 0,
                "duration_ms": 8000,
                "tools_used": [],
                "status": "error",
                "error": "Model context length exceeded: maximum 100K tokens",
                "error_type": "llm_input",
                "tool_name": None,
            },
        ],
    },
    {
        "name": "文档助手 - 5轮长对话后报错",
        "session_name": "项目文档撰写协助",
        "user_id": "multi-user-4",
        "user_name": "赵六",
        "bbk_id": "400",
        "channel": "console",
        "rounds": [
            {
                "user_message": "帮我写一个项目立项报告的开头部分",
                "model_output": "好的，以下是项目立项报告的开头部分：\n\n## 项目立项报告\n\n### 1. 项目背景\n本项目旨在开发一套智能数据分析平台，用于支持业务部门的日常数据查询和分析需求。\n\n### 2. 项目目标\n- 建立统一的数据查询入口\n- 提供可视化的数据分析工具\n- 实现自动化报表生成\n\n您需要继续完善哪些部分？",
                "model_name": "qwen-2.5",
                "input_tokens": 50,
                "output_tokens": 180,
                "duration_ms": 4000,
                "tools_used": [],
                "status": "completed",
            },
            {
                "user_message": "帮我补充技术方案部分",
                "model_output": "### 3. 技术方案\n\n#### 3.1 系统架构\n采用前后端分离架构，前端使用React框架，后端使用Python FastAPI。\n\n#### 3.2 数据存储\n使用MySQL作为主数据库，Redis作为缓存层，Elasticsearch用于日志搜索。\n\n#### 3.3 核心模块\n- 数据查询模块：支持SQL和自然语言查询\n- 报表生成模块：支持PDF/Excel导出\n- 权限管理模块：基于角色的访问控制",
                "model_name": "qwen-2.5",
                "input_tokens": 100,
                "output_tokens": 250,
                "duration_ms": 6000,
                "tools_used": [],
                "status": "completed",
            },
            {
                "user_message": "继续补充人员配置和预算部分",
                "model_output": "### 4. 人员配置\n\n#### 4.1 团队组成\n- 项目经理：1人\n- 前端开发：2人\n- 后端开发：3人\n- 测试工程师：1人\n- 产品经理：1人\n\n### 5. 项目预算\n\n#### 5.1 人力成本\n预计总人力投入8人月，按照人均成本2万元/月计算，人力成本约16万元。\n\n#### 5.2 基础设施成本\n服务器、云服务、软件license等预计5万元。\n\n#### 5.3 总预算\n项目总预算约21万元。",
                "model_name": "qwen-2.5",
                "input_tokens": 120,
                "output_tokens": 200,
                "duration_ms": 5000,
                "tools_used": [],
                "status": "completed",
            },
            {
                "user_message": "帮我补充风险评估和时间计划",
                "model_output": "### 6. 风险评估\n\n#### 6.1 技术风险\n- 数据源对接可能存在兼容性问题\n- 高并发场景下性能挑战\n\n#### 6.2 应对措施\n- 提前进行数据源调研\n- 设计可扩展的架构\n\n### 7. 时间计划\n\n#### 7.1 阶段划分\n| 阶段 | 内容 | 时间 |\n|------|------|------|\n| 需求分析 | 确定功能需求 | 2周 |\n| 设计阶段 | 架构设计、UI设计 | 3周 |\n| 开发阶段 | 编码实现 | 8周 |\n| 测试阶段 | 功能测试、性能测试 | 2周 |\n| 上线阶段 | 部署上线 | 1周 |\n\n项目总周期预计16周。",
                "model_name": "qwen-2.5",
                "input_tokens": 150,
                "output_tokens": 220,
                "duration_ms": 7000,
                "tools_used": [],
                "status": "completed",
            },
            {
                "user_message": "能帮我把整个报告整合成一个完整的文档吗？",
                "model_output": None,  # 报错轮次
                "model_name": "qwen-2.5",
                "input_tokens": 500,
                "output_tokens": 0,
                "duration_ms": 10000,
                "tools_used": ["doc_generator"],
                "status": "error",
                "error": "Document generation failed: file system permission denied",
                "error_type": "tool_call_end",
                "tool_name": "doc_generator",
            },
        ],
    },
    {
        "name": "MCP工具调用 - 多轮后MCP报错",
        "session_name": "数据库查询服务",
        "user_id": "multi-user-5",
        "user_name": "孙七",
        "bbk_id": "500",
        "channel": "api",
        "rounds": [
            {
                "user_message": "查询客户表中前10条记录",
                "model_output": "好的，查询结果如下：\n| id | name | email | created_at |\n|----|------|-------|------------|\n| 1 | 张三 | zhang@example.com | 2024-01-01 |\n| 2 | 李四 | li@example.com | 2024-02-15 |\n| ...共10条记录",
                "model_name": "gpt-4o",
                "input_tokens": 40,
                "output_tokens": 100,
                "duration_ms": 3000,
                "tools_used": ["mysql_query"],
                "status": "completed",
                "mcp_server": "mysql_server",
            },
            {
                "user_message": "查询订单表中金额大于1000的订单",
                "model_output": "查询到15条符合条件的订单，总金额约28500元。最近一笔是昨天下午的订单，金额1500元。",
                "model_name": "gpt-4o",
                "input_tokens": 60,
                "output_tokens": 80,
                "duration_ms": 2500,
                "tools_used": ["mysql_query"],
                "status": "completed",
                "mcp_server": "mysql_server",
            },
            {
                "user_message": "帮我生成一个客户消费分析报告",
                "model_output": None,  # 报错轮次
                "model_name": "gpt-4o",
                "input_tokens": 100,
                "output_tokens": 0,
                "duration_ms": 5000,
                "tools_used": ["mysql_query", "data_analysis"],
                "status": "error",
                "error": "MCP server mysql_server connection lost during analysis",
                "error_type": "tool_call_end",
                "tool_name": "data_analysis",
                "mcp_server": "mysql_server",
            },
        ],
    },
]


async def insert_trace(
    db: DatabaseConnection,
    trace_id: str,
    session_id: str,
    source_id: str,
    round_data: dict,
    round_index: int,
    base_time: datetime,
    session_name: str,
    user_id: str,
    user_name: str,
    bbk_id: str,
    channel: str,
) -> int:
    """插入一个 Trace 记录."""
    trace_start = base_time + timedelta(minutes=round_index * 5)
    trace_end = trace_start + timedelta(milliseconds=round_data["duration_ms"])

    # 计算 tokens
    total_input = round_data.get("input_tokens", 0)
    total_output = round_data.get("output_tokens", 0)

    # 构建查询
    query = """
        INSERT INTO swe_tracing_traces (
            trace_id, source_id, user_id, user_name, bbk_id,
            session_id, session_name, channel, start_time, end_time,
            duration_ms, model_name, total_input_tokens, total_output_tokens,
            tools_used, skills_used, status, error, user_message
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """

    params = (
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
        round_data["duration_ms"],
        round_data["model_name"],
        total_input,
        total_output,
        json.dumps(round_data.get("tools_used", [])),
        json.dumps([]),  # skills_used
        round_data["status"],
        round_data.get("error"),
        round_data["user_message"],
    )

    await db.execute(query, params)

    # 插入 spans
    span_count = 0

    # 用户消息 span（模拟 session_start）
    span_count += 1

    # 工具调用 spans
    for tool in round_data.get("tools_used", []):
        tool_span_id = str(uuid.uuid4())
        is_error_tool = (
            round_data.get("tool_name") == tool
            and round_data.get("error_type") == "tool_call_end"
        )

        tool_query = """
            INSERT INTO swe_tracing_spans (
                span_id, trace_id, source_id, name, event_type,
                start_time, end_time, duration_ms, user_id, user_name, bbk_id,
                session_id, channel, model_name, input_tokens, output_tokens,
                tool_name, mcp_server, error
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        tool_params = (
            tool_span_id,
            trace_id,
            source_id,
            f"tool_{tool}",
            "tool_call_end",
            trace_start + timedelta(milliseconds=100),
            trace_start
            + timedelta(milliseconds=round_data["duration_ms"] - 100),
            round_data["duration_ms"] - 200,
            user_id,
            user_name,
            bbk_id,
            session_id,
            channel,
            round_data["model_name"],
            None,
            None,
            tool,
            round_data.get("mcp_server"),
            round_data.get("error") if is_error_tool else None,
        )
        await db.execute(tool_query, tool_params)
        span_count += 1

    # LLM 调用 span
    llm_span_id = str(uuid.uuid4())
    is_llm_error = round_data.get("error_type") == "llm_input"

    llm_query = """
        INSERT INTO swe_tracing_spans (
            span_id, trace_id, source_id, name, event_type,
            start_time, end_time, duration_ms, user_id, user_name, bbk_id,
            session_id, channel, model_name, input_tokens, output_tokens, error
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """
    llm_params = (
        llm_span_id,
        trace_id,
        source_id,
        "llm_call",
        "llm_input",
        trace_start,
        trace_end,
        round_data["duration_ms"],
        user_id,
        user_name,
        bbk_id,
        session_id,
        channel,
        round_data["model_name"],
        round_data.get("input_tokens"),
        round_data.get("output_tokens"),
        round_data.get("error") if is_llm_error else None,
    )
    await db.execute(llm_query, llm_params)
    span_count += 1

    # 写入 model_output 到 ES（暂时跳过，不影响多轮对话展示测试）
    # if round_data.get("model_output"):
    #     try:
    #         from monitor.app.database.elasticsearch import get_es_client
    #         es_client = get_es_client()
    #         if es_client:
    #             await es_client.index_message(trace_id, round_data["model_output"])
    #     except Exception:
    #         pass

    return span_count


async def main():
    """主函数."""
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
    db = DatabaseConnection(config)
    await db.connect()

    print("=" * 60)
    print("多轮对话测试数据脚本")
    print("=" * 60)

    total_traces = 0
    total_spans = 0
    base_time = datetime.now() - timedelta(hours=2)

    for scenario in MULTI_ROUND_SCENARIOS:
        print(f"\n=== {scenario['name']} ===")
        session_id = str(uuid.uuid4())
        source_id = random.choice(SOURCE_IDS)

        for i, round_data in enumerate(scenario["rounds"]):
            trace_id = str(uuid.uuid4())
            status = round_data["status"]

            span_count = await insert_trace(
                db=db,
                trace_id=trace_id,
                session_id=session_id,
                source_id=source_id,
                round_data=round_data,
                round_index=i,
                base_time=base_time,
                session_name=scenario["session_name"],
                user_id=scenario["user_id"],
                user_name=scenario["user_name"],
                bbk_id=scenario["bbk_id"],
                channel=scenario["channel"],
            )

            total_traces += 1
            total_spans += span_count

            status_icon = "[OK]" if status == "completed" else "[ERR]"
            print(
                f"  第{i + 1}轮: {status_icon} {round_data['user_message'][:30]}... | {trace_id[:16]}...",
            )

    print("\n" + "=" * 60)
    print("插入完成:")
    print(f"  - 会话数: {len(MULTI_ROUND_SCENARIOS)} 个")
    print(f"  - Trace 记录: {total_traces} 条")
    print(f"  - Span 记录: {total_spans} 条")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
