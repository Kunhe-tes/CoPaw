## Context

`SafeJSONSession` exposes async persistence methods, but
`save_session_state()` and `update_session_state()` finish with synchronous
`open()` and `write()` calls on the event-loop thread. `save_merged_state()`
uses `aiofiles`, so session writes currently have inconsistent offloading
behavior.

Several methods also perform read-modify-write sequences without coordination.
Two tasks targeting the same session JSON path can both read the same old
state, then write different results, causing the later write to silently erase
the earlier update. `save_session_skill_snapshot()` has the same risk because
it reads the full state and later saves the merged document.

The repository already uses a loop-and-path keyed `asyncio.Lock` registry for
file writes in `src/swe/agents/tools/file_io.py`. Session persistence should
follow that established concurrency model.

## Goals / Non-Goals

**Goals:**

- Move every session JSON filesystem write off the event-loop thread with
  `asyncio.to_thread()`.
- Serialize all writes targeting the same effective session path.
- Keep each read-modify-write sequence inside the same per-path critical
  section so concurrent updates are preserved.
- Preserve current async public method signatures, JSON format, filename
  sanitization, and missing/invalid-state behavior.
- Allow writes to different session paths to proceed concurrently.

**Non-Goals:**

- Add cross-process or distributed locking across application instances.
- Change pure session read methods to use `asyncio.to_thread()`.
- Introduce atomic temporary-file replacement, journaling, or a new storage
  backend.
- Change full-state overwrite semantics for callers of `save_merged_state()`.

## Decisions

### Use a module-level loop-and-path lock registry

Add a helper that returns an `asyncio.Lock` keyed by the running event loop and
the normalized absolute session path. Protect lock creation with a small
`threading.Lock`, matching the established `file_io.py` pattern.

This coordinates separate `SafeJSONSession` instances that target the same
file while avoiding reuse of an `asyncio.Lock` across different event loops.
An instance-local lock map was rejected because multiple runner/session
instances can share a save directory and would not coordinate.

### Use one synchronous JSON write helper through `asyncio.to_thread()`

Add a synchronous helper responsible only for opening the target path and
writing the already-serialized JSON text. Every session write entry point will
await that helper through `asyncio.to_thread()`.

Serializing state with `json.dumps()` remains on the event-loop thread because
the requested change targets blocking filesystem writes, and moving state
serialization would complicate state-module access without addressing the
current file-I/O issue. Continuing to use `aiofiles` for writes was rejected so
all session writes have one explicit and testable offloading path.

### Lock complete read-modify-write operations

`save_session_state()` and `update_session_state()` will acquire the path lock
before reading existing JSON and hold it until the offloaded write completes.
This prevents two writers from deriving results from the same stale state.

`save_session_skill_snapshot()` will delegate to the coordinated top-level key
update operation instead of reading and then overwriting the full state through
`save_merged_state()`. `save_merged_state()` remains a full-state overwrite,
but its write is serialized under the same path lock.

Pure read methods remain unlocked. Writer coordination addresses lost updates
between writers without expanding the scope into reader consistency or atomic
file replacement.

### Preserve path-local concurrency

The lock is selected only after deriving the final sanitized save path. Tasks
writing different paths therefore acquire different locks and can overlap.
There will be no global session-write lock.

## Risks / Trade-offs

- [Risk] Locks coordinate only within one Python process. Multiple Kubernetes
  processes writing the same underlying file can still race. → Keep
  cross-process coordination out of scope and retain the existing deployment
  assumption that a session file has one process-local owner.
- [Risk] The module-level lock registry can grow with the number of unique
  loop/path pairs. → Accept the bounded process-lifetime trade-off, consistent
  with the existing file-write lock registry; revisit eviction only if metrics
  show meaningful growth.
- [Risk] An unlocked reader can observe a file while an offloaded writer is
  replacing its contents. → Preserve current behavior because atomic
  replacement and reader locking are separate changes.
- [Risk] Cancellation while awaiting `to_thread()` does not stop an already
  running filesystem write. → Hold the path lock until the awaited operation
  resolves under normal execution and document no stronger cancellation
  guarantee.
