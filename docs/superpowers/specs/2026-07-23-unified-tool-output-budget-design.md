# Unified Tool Output Budget Design

## Goal

For streamed shell-tool output that exceeds its configured budget, the frontend
tool card and the next Main Agent reasoning turn must receive the same
canonical, bounded representation. Neither must silently see content that the
other cannot see.

## Scope

This changes the `execute_shell_command` live-output path. It preserves the
existing live-frame event contract, terminal-result precedence, reconnect
behavior, tool status, and completed-history rebuilding. It does not add live
output for other tools.

## Canonical Output Representation

The backend will derive one display-and-context-safe textual result for a tool
invocation:

- keep a configurable leading excerpt and trailing excerpt;
- replace omitted middle content with one stable marker;
- include enough metadata in the marker to make truncation explicit, including
  original byte count and omitted byte count;
- keep UTF-8 boundaries valid;
- apply the same byte and line budgets to stdout and stderr in their observed
  sequence.

The canonical representation is the only tool text sent in live frames after
the budget is reached, persisted as the terminal tool result, and supplied to
the next model call. The unbounded process output remains local to the shell
execution/audit boundary and is not retained in frontend state or agent memory.

## Data Flow

1. The shell reader collects ordered stdout/stderr chunks for command
   completion and feeds them to an invocation-local output normalizer.
2. Before the stream budget is exceeded, the normalizer emits normal live
   frames. On completion it materializes the canonical head-and-tail result.
3. The terminal tool result uses that canonical result, so it is the exact
   value stored in agent memory and supplied to the following reasoning turn.
4. The frontend appends live frames while the command runs, then replaces the
   temporary area with the canonical terminal result as it does today.
5. The browser retains a defensive size check for malformed, legacy, or replay
   input. With server-produced frames and results it must be idempotent: it
   cannot change already canonical content.

## Budget And Compatibility

The server owns the configured budget and omission marker. The frontend must
not independently choose a different normal retention policy. Existing clients
continue to receive `tool_output_frame` and ordinary terminal tool-result
events; the new metadata is additive. Completed history remains based on final
tool results only.

## Error Handling

Successful, failed, and timeout shell invocations all use the same
normalization rule. If no final result is available after cancellation, the
last bounded live result remains visible, as today. Normalization failures must
fall back to a bounded marker rather than leaking the original unbounded text.

## Test Strategy

- Backend unit tests cover exact-boundary, over-budget, multi-byte UTF-8,
  line-budget, and stdout/stderr ordering cases.
- A tool-execution regression test verifies that an over-budget shell result
  stored for the next Agent loop equals the terminal visible result and carries
  one omission marker.
- Frontend tests verify that server-canonical output survives the defensive
  guard unchanged, while malformed oversized frames remain bounded.
- Existing live-stream, terminal-result, reconnect, and shell timeout tests
  remain green.

## Non-Goals

- Retaining full shell output in model context or browser state.
- Changing ordinary non-streaming tool result compaction.
- Changing output budgets for MCP, file-read, browser, or structured tools.
