## 1. Session Write Regression Tests

- [x] 1.1 Add focused `SafeJSONSession` tests proving filesystem writes run through `asyncio.to_thread()` without blocking unrelated event-loop work.
- [x] 1.2 Add concurrency tests proving same-path writes serialize across session objects while different-path writes can overlap.
- [x] 1.3 Add read-modify-write concurrency tests proving key updates and skill snapshot saves preserve other coordinated state updates.

## 2. Coordinated Session Persistence

- [x] 2.1 Add a loop-and-normalized-path keyed `asyncio.Lock` registry with thread-safe lock creation in `src/swe/app/runner/session.py`.
- [x] 2.2 Add one synchronous JSON filesystem write helper and route every session write entry point through `asyncio.to_thread()`.
- [x] 2.3 Hold the per-path lock across complete read-modify-write operations in `save_session_state()` and `update_session_state()`.
- [x] 2.4 Route skill snapshot persistence through the coordinated key-update path and serialize `save_merged_state()` writes with the same per-path lock.

## 3. Verification

- [x] 3.1 Run the focused `SafeJSONSession` unit tests and fix any failures.
- [x] 3.2 Run existing runner session-skill freshness and hook-runtime tests to verify persistence behavior remains compatible.
- [x] 3.3 Run the relevant broader unit-test subset and inspect GitNexus changed-symbol impact before completion.
