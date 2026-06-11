## Why

`src/swe/agents/tools/file_io.py` exposes async file tools, but its write path
still relies on synchronous filesystem calls. Slow writes can therefore occupy
the event-loop thread even though callers use `await`, which is a mismatch for
tool execution inside the agent runtime.

## What Changes

- Offload `write_file` and `append_file` filesystem writes so slow writes do
  not block unrelated event-loop work.
- Preserve the existing per-path lock, temp-file replace flow, and cancellation
  behavior that prevents partially written target files.
- Keep the current public tool interfaces, encoding rules, and append
  read-modify-write semantics.
- Add focused tests covering non-blocking writes, cancellation safety, and
  compatibility of the existing diagnostics.

## Capabilities

### New Capabilities

- `file-tool-nonblocking-writes`: Defines non-blocking write execution for the
  `write_file` and `append_file` tools while preserving their current atomic
  replacement and cancellation guarantees.

### Modified Capabilities

None.

## Impact

- Affected code: `src/swe/agents/tools/file_io.py`.
- Affected tests: `tests/unit/agents/test_file_io_cancellation.py`,
  `tests/unit/agents/test_phase_aware_watchdog.py`, and the focused file-tool
  workspace tests.
- Runtime dependency: reuse the existing `aiofiles` dependency already present
  in the project.
- Public tool names, argument shapes, and success/error response formats remain
  unchanged.
