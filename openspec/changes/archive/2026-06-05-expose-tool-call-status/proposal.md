## Why

During a live chat turn, the backend streams tool call and tool output messages but does not provide a stable backend-owned status that tells the frontend whether each user-visible tool invocation is running, succeeded, or failed. The frontend should not infer tool success or failure by parsing tool output text, and completed chat history should show the same final status when a user reopens a session.

## What Changes

- Add a backend presentation contract for Tool Call Status on existing tool message `content[].data` payloads.
- Mark user-visible tool call start messages with `tool_status: "running"`.
- Mark user-visible tool output messages with terminal `tool_status: "success"` or `tool_status: "failed"`.
- Attach `tool_error` to tool output messages, with `null` for success and a bounded non-empty Tool Error Summary for failure.
- Rebuild the same status fields when reading saved chat history, without persisting `tool_status` or `tool_error` into agent memory.
- Keep backend-silent tools hidden from the chat stream and history presentation.
- No frontend implementation is included in this change.

## Capabilities

### New Capabilities

- `tool-call-status-presentation`: Define how backend chat streams and chat history payloads expose user-visible tool invocation lifecycle status.

### Modified Capabilities

- None.

## Impact

- Affected code:
  - `src/swe/app/runner/stream_boundary.py`
  - `src/swe/app/runner/utils.py`
  - a new runner-level tool status normalization module
  - related unit tests under `tests/unit/app/`
- API contract:
  - Existing SSE and chat history message payloads gain backward-compatible fields inside tool message `content[].data`.
- Persistence:
  - No database migration and no agent memory schema change are expected.
- Dependencies:
  - No new third-party dependencies are expected.
