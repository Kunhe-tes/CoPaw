## Why

`SafeJSONSession` still performs synchronous JSON file writes directly on the
event-loop thread, and its read-modify-write operations are not coordinated.
Concurrent writes to the same session path can therefore block unrelated async
work and overwrite each other's state.

## What Changes

- Offload every `SafeJSONSession` JSON file write through
  `asyncio.to_thread()` so filesystem writes do not block the event loop.
- Serialize writes and read-modify-write operations per resolved session path
  with an `asyncio.Lock`, while allowing different session paths to proceed
  independently.
- Make session skill snapshot persistence use the coordinated state-update path
  so it cannot overwrite concurrent session state changes.
- Add focused concurrency and offloading tests for session persistence.

## Capabilities

### New Capabilities

- `session-state-write-coordination`: Defines non-blocking, per-path coordinated
  session JSON writes and preservation of concurrent state updates.

### Modified Capabilities

None.

## Impact

- Affected code: `src/swe/app/runner/session.py`.
- Affected tests: focused unit tests for `SafeJSONSession` persistence and
  existing runner/session skill snapshot tests.
- Public async method signatures and persisted JSON structure remain unchanged.
- No new runtime dependency is required.
