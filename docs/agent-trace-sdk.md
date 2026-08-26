# AgentTraceSDK 接入

Swe 仅使用 `trace_design.md` 中定义的 AgentTraceSDK API，为一条用户消息的 Main Agent 执行生成 `agent.run` 根 Span。子 Span 覆盖准入、每次执行尝试、模型调用和实际执行的工具调用；原有 `swe.tracing` 链路保持不变。

部署时从私有制品源安装项目声明的 `LR34.05-AgentTraceSDK` 依赖。默认关闭采集：

```bash
AGENT_TRACE_ENABLED=false
AGENT_TRACE_SERVICE_NAME=swe-agent
AGENT_TRACE_EXPORTER=console
AGENT_TRACE_ATTRIBUTE_REDACTION_ENABLED=true
AGENT_TRACE_ATTRIBUTE_VALUE_REDACTION_ENABLED=true
```

本期验证时显式启用 Console exporter：

```bash
AGENT_TRACE_ENABLED=true
AGENT_TRACE_EXPORTER=console
```

不配置 HTTP exporter、端点或认证信息。

采集约束如下：记录原始用户问题与工具输入（包括 shell 命令正文）；不记录模型完整输出和工具原始输出。属性脱敏和属性值脱敏均显式开启，默认结构深度为 5。
