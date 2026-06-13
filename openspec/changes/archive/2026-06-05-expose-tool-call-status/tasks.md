## 1. Preparation

- [x] 1.1 Run GitNexus impact analysis for the stream normalization and history conversion symbols before editing them.
- [x] 1.2 Inspect current live tool event data and saved `tool_use` / `tool_result` history conversion shapes to confirm field names used by tests.

## 2. Status Normalization

- [x] 2.1 Add a runner-level pure `tool_status` normalization module with constants for `running`, `success`, `failed`, `tool_status`, `tool_error`, and a 500-character error summary limit.
- [x] 2.2 Implement helper logic to mark tool call-start data as `tool_status: "running"` without adding `tool_error`.
- [x] 2.3 Implement helper logic to resolve terminal tool output data to `success` or `failed`, including MCP/dict `isError`, explicit `error`, generic fallback error text, and bounded `tool_error`.
- [x] 2.4 Add pure function unit tests for running status, success output, failed output, default failed error text, and 500-character truncation.

## 3. Live Stream Integration

- [x] 3.1 Update stream tool message enrichment to call the shared status normalization helpers for function, plugin, and MCP tool call events.
- [x] 3.2 Update stream tool output enrichment to attach terminal `tool_status` and `tool_error` while preserving existing `output_summary` behavior.
- [x] 3.3 Keep backend-silent tool filtering ahead of status enrichment so silent tools still emit no tool status fields.
- [x] 3.4 Add live stream tests for call running status, output success status, output failed status, and silent tool filtering.

## 4. Chat History Integration

- [x] 4.1 Update history conversion for saved `tool_use` records to rebuild `tool_status: "running"` in returned `ChatMessage` data.
- [x] 4.2 Update history conversion for saved `tool_result` records to rebuild terminal `tool_status` and `tool_error` in returned `ChatMessage` data.
- [x] 4.3 Ensure history conversion does not require or persist `tool_status` / `tool_error` in agent memory.
- [x] 4.4 Add history read conversion tests for saved tool use, successful tool result, and failed tool result.

## 5. Verification

- [x] 5.1 Run the targeted unit tests for tool status normalization, stream boundary behavior, and history conversion.
- [x] 5.2 Run `openspec status --change "expose-tool-call-status"` and confirm the change is apply-ready.
- [x] 5.3 Run `gitnexus_detect_changes()` before any commit to confirm affected symbols and flows match the expected stream/history scope.
