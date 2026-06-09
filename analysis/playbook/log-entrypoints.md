# 日志入口

本文档记录运行时问题最常用的日志与快照入口。

## 运行时日志主入口

当前运行时日志以进程 `stdout/stderr` 为主入口。默认情况下，运维排查应优先查看容器日志、Supervisor 日志、systemd journal，或直接查看进程标准输出/标准错误。

## `WORKING_DIR/swe.log` 条件

`WORKING_DIR/swe.log` 仅在 `SWE_FILE_LOG_ENABLED=true` 时生成并持续写入。未开启该开关时，不应将 `swe.log` 视为稳定日志来源。

## daemon 日志命令行为

`/daemon logs` 与 `swe daemon logs` 仅在文件日志启用时读取 `swe.log`。当 `SWE_FILE_LOG_ENABLED` 未开启时，这两个入口不会返回运行时日志内容，只会提示运维改为检查容器日志、Supervisor 日志、systemd journal 或进程 `stdout/stderr`。

## Hook telemetry

Hook 机制的埋点以运行时日志为入口，不写入 `swe_tracing_spans`。当至少一个 hook handler 实际执行时，`src/swe/agents/hook_runtime/runtime.py` 会输出 INFO 级单行日志，消息体以固定前缀 `HOOK_TELEMETRY ` 开头，后面紧跟 JSON payload。

排查 hook 行为时优先按 `HOOK_TELEMETRY ` 前缀过滤日志，再解析 JSON 中的 `schema`、`hook_event_name`、`trace_id`、`session_id`、`tool_name`、`decision`、`blocked`、`handlers`、`permission_decisions` 等字段。payload 只保留结构化元数据和脱敏/截断预览，不应作为原始 prompt、tool input、tool output 或 handler output 的来源。

## query error dump

`query error dump` 仍可作为请求级故障快照入口，用于补充上下文与失败栈信息，但不替代运行时主日志入口。
