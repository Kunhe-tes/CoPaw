## Context

`src/swe/agents/tools/file_io.py` already exposes async tool functions and uses
per-path `asyncio.Lock` coordination plus temp-file replacement to protect
writes. The remaining mismatch is that the actual disk write still happens via
synchronous file handles. That can occupy the event-loop thread during slow
writes even though the public API is async.

The user request is narrower than a full file-I/O cleanup: use `aiofiles` to
make tool writes non-blocking, but stay with the conservative scope we agreed
on. `append_file()` currently performs a read-modify-write sequence by reading
existing content and then delegating to the same atomic write path. That read
already runs off the event-loop thread through `asyncio.to_thread()`, so the
main gap is the write side.

## Goals / Non-Goals

**Goals:**

- Move the `write_file` and `append_file` disk-write phase off the event-loop
  thread by using `aiofiles`.
- Preserve the existing per-path locking, temp-file replacement, and
  cancellation semantics.
- Preserve the current tool response format, path resolution rules, and file
  encoding selection behavior.
- Keep existing diagnostics and focused tests compatible with the new write
  path.

**Non-Goals:**

- Convert every file read in `file_io.py` to `aiofiles`.
- Change `append_file()` from its current read-modify-write behavior to true
  OS-level append mode.
- Introduce cross-process write coordination or a new storage abstraction.
- Change tool names, arguments, or error payload structure.

## Decisions

### Use `aiofiles` only in the shared write helper

The shared helper currently responsible for opening the temp file, writing
content, and emitting timing diagnostics will become the `aiofiles` boundary.
This is the narrowest point that removes event-loop blocking from both
`write_file` and `append_file` without changing their public contract.

Rejected alternative: switch the whole module to `aiofiles`, including reads.
That would increase change surface and test churn without improving the specific
problem the user asked to solve.

### Keep the existing temp-file + `os.replace()` atomic write flow

The write helper change will happen underneath the existing
`_write_file_atomically_unlocked()` flow. The system will still create a temp
file in the target directory, write the full content there, and replace the
target only after the temp write succeeds.

Rejected alternative: write directly to the target file through `aiofiles`.
That would weaken the current protection against partial target-file updates and
would invalidate existing cancellation expectations.

### Preserve append read semantics and only change the blocking write phase

`append_file()` will continue to read the existing file content before writing
the merged content through the atomic replacement path. The read phase already
avoids event-loop blocking through `asyncio.to_thread()`, so the conservative
plan does not replace it.

Rejected alternative: also convert the read phase to `aiofiles` for stylistic
consistency. That is a broader refactor than needed for this change and makes
the write-focused regression target less clear.

### Retain diagnostic logging structure

The write helper will continue to measure resolve/open/write/close timing and
log only metadata such as byte counts and durations. The implementation of the
timing boundaries can shift to awaitable operations, but the emitted diagnostic
shape should remain stable so current watchdog and observability tests still
validate behavior.

Rejected alternative: simplify logging while touching the helper. That would
mix observability changes into a targeted I/O change and reduce confidence in
regression tests.

## Risks / Trade-offs

- [Risk] `aiofiles` still delegates work through background threads, so this is
  not a fundamentally different filesystem model. → Mitigation: that is
  acceptable because the goal is specifically to avoid blocking the event loop,
  not to redesign storage behavior.
- [Risk] Cancellation can happen between awaited write phases and final
  replacement. → Mitigation: keep the existing shield/cleanup structure and
  validate it with the current cancellation regression tests.
- [Risk] Timing measurements may shift slightly when using awaitable file
  operations. → Mitigation: keep the same diagnostic fields and verify tests
  assert structure and secrecy, not exact timing values.

## Migration Plan

1. Update the shared temp-file write helper in `file_io.py` to use `aiofiles`.
2. Keep the existing append read path and atomic replacement control flow.
3. Run the focused file-tool regression tests covering cancellation,
   diagnostics, and event-loop progress.

Rollback is straightforward: revert the helper change and tests, because no
public API or persisted file format changes.

## Open Questions

None.
