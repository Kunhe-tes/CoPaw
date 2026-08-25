# AgentTraceSDK 接入

Swe 仅使用 `trace_design.md` 中定义的 AgentTraceSDK API，为一条用户消息的 Main Agent 执行生成 `agent.run` 根 Span。子 Span 覆盖准入、每次执行尝试、模型调用和已批准工具调用；原有 `swe.tracing` 链路保持不变。

部署时从私有制品源安装项目声明的 `LR34.05-AgentTraceSDK` 依赖，并在进程启动前设置：

```bash
AGENT_TRACE_ENABLED=true
AGENT_TRACE_SERVICE_NAME=swe-agent
AGENT_TRACE_EXPORTER=http
AGENT_TRACE_HTTP_ENDPOINT=<trace-endpoint>
AGENT_TRACE_ATTRIBUTE_REDACTION_ENABLED=true
AGENT_TRACE_ATTRIBUTE_VALUE_REDACTION_ENABLED=true
```

端点及其认证信息应通过部署系统的密钥配置注入，不能提交到仓库。

采集约束如下：记录原始用户问题与工具输入（包括 shell 命令正文）；不记录模型完整输出和工具原始输出。内容脱敏和长度保护由 SDK 文档指定的 exporter 配置负责。
