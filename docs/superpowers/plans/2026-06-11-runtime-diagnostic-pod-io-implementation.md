# Runtime Diagnostic Pod I/O Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Runtime Diagnostic with current-container open file descriptor count and cgroup disk read/write throughput without requiring root privileges or exposing Kubernetes node-level data.

**Architecture:** Add a focused Pod-resource collector that parses the current PID namespace and current process cgroup v1/v2 files. Extend `RuntimeDiagnosticManager` to sample cumulative cgroup I/O counters every second, derive latest and peak rates for each diagnostic window, and emit an instantaneous Pod FD count.

**Tech Stack:** Python, asyncio, Linux `/proc`, cgroup v1/v2, pytest

---

### Task 1: Pod Resource Collectors

**Files:**
- Create: `src/swe/app/pod_resources.py`
- Create: `tests/unit/app/test_pod_resources.py`

- [ ] Write failing tests for complete PID namespace FD summation, partial FD scan failure, cgroup v2 `io.stat`, cgroup v1 blkio service bytes, and unreadable cgroup files.
- [ ] Run `../../venv/bin/python -m pytest tests/unit/app/test_pod_resources.py -v` and verify RED.
- [ ] Implement `collect_pod_open_fd_count()` and `collect_pod_disk_io_bytes()` using injected filesystem roots/readers for deterministic tests.
- [ ] Run `../../venv/bin/python -m pytest tests/unit/app/test_pod_resources.py -v` and verify GREEN.

### Task 2: Diagnostic Window Integration

**Files:**
- Modify: `src/swe/app/runtime_diagnostic.py`
- Modify: `tests/unit/app/test_runtime_diagnostic.py`

- [ ] Write failing tests for latest/peak disk-I/O rates, first-sample baseline behavior, window rotation, invalid sample nulling, and `pod_open_fd_count`.
- [ ] Run the new Runtime Diagnostic tests and verify RED.
- [ ] Inject the Pod collectors, sample cumulative counters every second, preserve the counter baseline across rotations, and emit the five confirmed nullable fields.
- [ ] Run Runtime Diagnostic tests and verify GREEN.

### Task 3: Contract Documentation And Verification

**Files:**
- Modify: `analysis/playbook/log-entrypoints.md`
- Modify: `analysis/observability-and-supporting-systems.md`
- Modify: `docs/superpowers/specs/2026-06-09-runtime-diagnostic-design.md`

- [ ] Document that Pod FD and disk-I/O metrics are current-container scoped, unprivileged, and nullable on incomplete reads.
- [ ] Run `git diff --check`, pre-commit checks, focused Runtime Diagnostic tests, and `tests/unit/app/`.
- [ ] Run GitNexus change detection and confirm affected existing flows remain limited to Runtime Diagnostic integration.
