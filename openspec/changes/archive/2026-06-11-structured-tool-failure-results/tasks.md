## 1. Failure contract primitives

- [x] 1.1 Add a shared `ToolExecutionError` contract with `error_type`, raw failure detail, and canonical content-block helpers.
- [x] 1.2 Add a shared builder for canonical structured failed `tool_result` payloads and mapped fallback error types.

## 2. Swe-controlled tool execution normalization

- [x] 2.1 Introduce a Swe-owned tool execution wrapper or toolkit extension that converts `ToolExecutionError`, known transport/runtime exceptions, and generic exceptions into structured failed tool results.
- [x] 2.2 Wire the Swe agent toolkit creation path to use the new exception-normalizing tool execution entrypoint without changing unrelated AgentScope behavior.

## 3. Migrate high-value failure producers

- [x] 3.1 Update built-in tool paths such as `shell`, `file_io`, and `copy_file_to_static` to raise `ToolExecutionError` instead of returning success-shaped plain-text failures.
- [x] 3.2 Update runtime-owned failure writers in `tool_guard_mixin` and related timeout/deny paths to emit canonical structured failed tool results through the shared builder.

## 4. Runner status compatibility and verification

- [x] 4.1 Update runner tool status derivation to prefer structured failed tool results, preserve pre-existing failed status in stream enrichment, and retain legacy plain-text fallback heuristics.
- [x] 4.2 Add unit coverage for explicit tool execution errors, generic exception fallback, MCP `isError`, hook denial, local hard timeout, shell/file-tool failure migration, and live-stream non-regression from failed to success.
