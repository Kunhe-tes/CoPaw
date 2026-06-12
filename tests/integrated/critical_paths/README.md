# Critical Runtime Path Tests

These tests are local contract/integration checks for code submission
validation. They do not call real external MCP or model services.

## Phase Order

1. `test_scheduled_run_boundary.py`
2. `test_mcp_runtime_path.py`
3. `test_model_invocation_path.py`
4. `test_scheduled_agent_mcp_react_path.py`

`scripts/run_critical_path_tests.py` runs these phases sequentially with
`pytest -x`. A failure in one phase stops later phases so the failing runtime
boundary can be analyzed first.

## Allowed Substitutions

- Loopback `127.0.0.1` FastMCP service for MCP servers.
- Deterministic bottom-level `ChatModelBase` returned by a fake Provider.
- Recording channel manager for channel delivery assertions.
- No-op or disabled monitor/tracing side effects.

## Forbidden Substitutions

- `CronManager._execute_once`
- `CronExecutor.execute` or `CronExecutor._execute_agent_job`
- `AgentRunner.stream_query` or `AgentRunner._prepare_query_runtime`
- `SWEAgent.reply` or `SWEAgent.register_mcp_clients`
- `HttpStatefulClient.connect`, `HttpStatefulClient.list_tools`, or
  `HttpStatefulClient.call_tool`
- `create_model_and_formatter`
- `RetryChatModel`

## MCP Availability Scope

Heartbeat and Dream execution do not require MCP availability. MCP
availability failures are asserted only in the MCP-specific phase and in
scheduled-agent scenarios that explicitly require an MCP tool.
