## Context

Console chat streaming currently sends existing runtime tool call and tool output messages through SSE. `TaskTracker` buffers in-flight SSE for reconnect, but completed chat detail is rebuilt later from persisted agent memory via the chat history API. Tool summaries are already added during stream normalization and history conversion, but tool lifecycle status is not exposed as a backend-owned field.

The design must make live stream, reconnect replay, and reopened chat history agree without adding frontend parsing requirements or persisting presentation-only fields into agent memory.

## Goals / Non-Goals

**Goals:**

- Expose Tool Call Status inside existing user-visible tool message `content[].data` payloads.
- Use `running`, `success`, and `failed` as the only first-version status values.
- Attach bounded Tool Error Summary values to failed terminal tool output messages.
- Rebuild the same presentation fields for chat history reads.
- Keep status/error normalization deterministic, synchronous, and independent from tool summary generation.

**Non-Goals:**

- No frontend implementation.
- No new SSE event type, route, database table, or agent memory schema.
- No generated tool call id when the runtime does not already provide one.
- No status for backend-silent tools.
- No cancellation status; user stop and external cancellation are not Tool Call Status failures.
- No error redaction beyond normalization and length bounding.

## Decisions

1. Attach status to existing tool message data rather than adding a new SSE event.

   The existing stream and chat history payloads already represent tool call starts and tool outputs. Adding `tool_status` and `tool_error` to `content[].data` is backward-compatible and keeps the frontend on one event stream. A separate event type would need additional ordering and replay rules.

2. Add a runner-level pure normalization module.

   A new runner module will provide deterministic helpers for applying `tool_status` and resolving terminal output status/error. Both stream normalization and history conversion will call this module. The implementation will not import `ToolGuardMixin` because that would couple app presentation logic to agent tool-guard tracing internals.

3. Treat persisted agent memory as source data, not presentation state.

   The runtime will not write `tool_status` or `tool_error` into durable agent memory. Live events gain presentation fields while streaming, and chat history reads rebuild those fields from saved `tool_use` and `tool_result` records. This keeps model memory clean and lets older histories gain status presentation when raw tool records contain enough information.

4. Terminal status comes only from tool output messages.

   Tool call start messages carry `tool_status: "running"`. Tool output messages carry `tool_status: "success"` or `tool_status: "failed"` and `tool_error`. If a run-level error terminates the stream without a tool output message, the backend will not fabricate a single-tool terminal status without reliable tool identity.

5. Failed means tool failure only.

   `failed` is assigned when backend normalization identifies a tool-result error, such as explicit error fields, MCP-style `isError`, or a tool exception represented in the output data. User stop, run cancellation, and stream disconnect are outside Tool Call Status.

## Risks / Trade-offs

- Live/history drift → Use one shared normalization module and test both paths against the same cases.
- Old history may lack enough raw failure metadata → Rebuild the best available status from persisted tool result data and default to success only when no error is identifiable.
- Error summary may expose more than intended → Bound to 500 characters and treat it as a user-visible summary, not a full diagnostic log; this change intentionally does not add redaction.
- No generated tool call id means concurrent same-name tools may be hard for frontend to correlate → First version keeps event-local status only and preserves any existing call id already present.
