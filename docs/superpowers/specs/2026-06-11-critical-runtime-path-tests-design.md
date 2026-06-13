# Critical Runtime Path Tests Design

## Goal

Add a local, repeatable validation stage for code submissions that exercises
the runtime paths most likely to regress when changing scheduled execution,
MCP wiring, or model invocation.

## Scope

This design covers local contract/integration tests only. It intentionally
does not call real external MCP servers, real model providers, or production
tenant services.

## Critical Paths

1. Scheduled run boundary: `CronExecutor.execute` binds tenant/source/workload
   context, builds agent requests with `skip_history=True`, sends text/events
   to the channel manager, and resets context afterward.
2. MCP runtime path: project `HttpStatefulClient` connects to a loopback
   FastMCP server, lists tools, calls a tool, and fails when required HTTP
   identity headers are absent.
3. Model invocation path: `ProviderManager -> create_model_and_formatter ->
   TokenRecordingModelWrapper -> RetryChatModel -> ChatModelBase` remains in
   the path; only the bottom provider-returned model is deterministic.
4. Scheduled Agent + MCP + ReAct path: `CronExecutor -> AgentRunner ->
   SWEAgent -> first model tool_use -> MCP tool result -> second model final
   reply -> Channel delivery -> cleanup`.

## Test Doubles

Allowed substitutions:

- Loopback `127.0.0.1` FastMCP service.
- Deterministic bottom-level `ChatModelBase` returned by a fake Provider.
- Recording channel manager.
- Disabled or absent tracing/monitor services.

Forbidden substitutions:

- `CronExecutor.execute` or `_execute_agent_job`.
- `AgentRunner.stream_query` or `_prepare_query_runtime`.
- `SWEAgent.reply` or `register_mcp_clients`.
- `HttpStatefulClient.connect`, `list_tools`, or `call_tool`.
- `create_model_and_formatter` or `RetryChatModel`.

## MCP Availability

MCP availability is not a prerequisite for Heartbeat or Dream execution.
MCP availability failures are diagnostic failures in the MCP-specific phase
and in scheduled-agent tests that explicitly require an MCP tool.

## Runner

`scripts/run_critical_path_tests.py` executes phases sequentially with
`pytest -x -v` and stops at the first failure. CI runs this script on Ubuntu
with Python 3.12 before the broader compatibility test jobs.
