# Tracing Bounded Writer Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, with TDD and review checkpoints.

**Goal:** Confirm all accepted Span versions before trace completion and shutdown, and bound the single writer's batches and outstanding work.

**Architecture:** Add `src/swe/tracing/writer.py` for queue ownership, versions, barriers, retries and drain. Integrate it into `manager.py`; make the existing Span batch store transactional and idempotent without migrating drivers.

**Tech Stack:** Python asyncio, Pydantic, existing aiomysql adapter, pytest.

---

### Task 1: Reproduce lifecycle gaps

- [x] Add `tests/unit/tracing/test_writer_lifecycle.py` using an Event-gated real manager/store seam. Check that `end_trace` cannot finish while INSERT is blocked, close waits for in-flight work, and an update during INSERT is confirmed before completion.
- [x] Run `PYTHONPATH=src ../../venv/bin/python -m pytest tests/unit/tracing/test_writer_lifecycle.py -q`; confirm failures match those gaps.

### Task 2: Implement confirmed lifecycle

- [x] Add `SpanWriter` entries with accepted/acknowledged versions, a single task, and trace barriers. Integrate initialize, emit, update, end and close; preserve pending cache access and source identity.
- [x] Make batch INSERT idempotent for stable Span IDs and wrap split SQL in a transaction. Keep mutable updates ordered and return confirmed processed count.
- [x] Run lifecycle tests plus `tests/unit/tracing` and correct regressions.

### Task 3: Bound work and cover failure paths

- [x] Add row/byte chunking, outstanding span/byte admission limits, cancellable backpressure, oversized-span isolation, capped retry backoff and explicit timeouts.
- [x] Add tests for full queues including in-flight capacity, byte chunks, oversized values, update failures, retries, cancellation, shutdown timeout, and isolation. Run new tests red before implementing the respective behavior.
- [x] Validate config limits and store transaction/upsert semantics with focused tests.

### Task 4: Verify and document

- [x] Run all tracing tests, database adapter tests and affected tracing SDK/runner contract tests using the project virtualenv and worktree PYTHONPATH.
- [x] Run pre-commit on changed files, inspect diff and GitNexus detect_changes, and update the Tracing playbook with actual behavior and limits.
- [x] Review the implementation for cancellation leaks, context inheritance, unbounded state and false completion. Deliver the verified changes with test evidence.

## Verification record

- Lifecycle, budget and real-adapter transaction seam: 35 passed, including cancellation followed by rollback failure and finite shutdown.
- Full tracing plus affected agent/app SDK, answer-turn, auxiliary trace-scope and tracing-chat API tests: 285 passed in 14.87 seconds.
- Changed-file pre-commit checks passed (AST, mypy, Black, flake8 and pylint included).
- Independent review found no remaining blocking issues after cancellation masking was fixed.
- GitNexus impact could not resolve manager/transaction symbols; detect_changes mapped the database class to unrelated frontend processes and reported CRITICAL. The graph result is not a reliable scope check. Source diff and the targeted regression suite were reviewed directly.
- No real MySQL integration or concurrent production load test was run. JSON serialization/driver escaping remain on the event loop; no production performance gain is claimed.
