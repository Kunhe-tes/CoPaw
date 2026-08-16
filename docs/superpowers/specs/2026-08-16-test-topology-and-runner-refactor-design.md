# Test Topology and AgentRunner Refactor Design

## Goal

Restore a trustworthy test and quality gate for the repository, then reduce
`AgentRunner` complexity without changing its externally observable behavior.
Follow with a separately validated cleanup tail-latency improvement.

All development and production validation in this change uses Python 3.12.
Python 3.10 and 3.13 compatibility are out of scope.

## Scope

This work has three deliverables:

1. Separate Swe, subproject, and cross-project contract tests.
2. Refactor `AgentRunner` into private query-execution collaborators while
   retaining its public and private facade boundaries.
3. In a later, independent change, parallelize non-dependent query cleanup
   work after session persistence.

It does not change HTTP responses, SSE event ordering, Hook or approval
semantics, retry rules, timeout behavior, or request runtime assembly.

## Test and Quality-Gate Topology

### Test classes

| Class | Location and installation | Owner |
| --- | --- | --- |
| Swe product tests | Root `tests/`, installed from root package | Swe |
| Subproject unit tests | Each of `market`, `monitor`, and `scheduler`, installed from that project's package | Respective subproject |
| Cross-project contract tests | Dedicated contract test directory and CI job, with every participating package installed editable | Interface owner |

Pure subproject test files presently beneath `tests/unit/market`,
`tests/unit/monitor`, and `tests/unit/scheduler` move to their respective
projects. Tests that deliberately cross a package boundary, including the
Swe-Monitor cron skill-ID case, become explicit contract tests rather than
Swe unit tests.

### Root test behavior

The root pytest configuration collects only Swe-owned tests. Its root
`conftest.py` exposes only `src/`; it must not make sibling project source
trees implicitly importable.

Every Python CI job uses Python 3.12. Existing 3.10, 3.13, and multi-OS
compatibility matrix jobs are removed. The critical runtime-path test remains
an independent Python 3.12 gate.

Quality commands fail closed: Ruff, formatting/type checks, product tests,
subproject tests, and contract tests cannot be masked by a successful shell
fallback.

### Acceptance criteria

- A clean root environment can collect and run Swe tests without importing a
  sibling package.
- Each subproject test job installs and runs independently.
- Each contract job declares every package it needs.
- CI reports the failing ownership boundary directly.

## AgentRunner First-Phase Refactor

### Stable facade

`AgentRunner` remains the owner of workspace, session, chat manager, task
tracker, and trace context. `query_handler`, `stream_query`, and existing
private facade methods remain valid. `_prepare_query_runtime` remains in
`AgentRunner` as the stable runtime-assembly boundary.

### Private collaborators

The runner package gains focused private collaborators:

```text
AgentRunner facade
  -> query_preflight: approvals, Hooks, command-path decision
  -> query_attempt: retry loop, one attempt, cancellation and error routing
  -> turn_lifecycle: prompt rebuild, turn plan, agent stream, completion gate
  -> session_lifecycle: session load/save, skill snapshots, cron-state merge
  -> query_cleanup: cleanup sequencing
```

Collaborators exchange explicit dataclasses, narrow Protocols, and callbacks.
They must not import `AgentRunner` at runtime or acquire global singleton
ownership. This prevents new dependency cycles while keeping orchestration
ownership visible at the facade.

### Behavioral contract

The first phase is strictly behavior preserving. It retains:

- HTTP and SSE response/event ordering;
- trace start/end status;
- approval, command, and Hook blocking behavior;
- retry/backoff and timeout behavior;
- cancellation handling;
- cleanup order: save session, update chat, close MCP clients, end skill
  detector.

### Verification

Before moving each boundary, characterization tests cover normal completion,
Hook block, approval short circuit, command path, retryable failure, final
failure, cancellation, and cleanup failure/timeout. They assert output event
traces, persistence-call order, and trace status. Existing critical runtime
path tests remain required.

## Cleanup Tail-Latency Second Phase

This is a separate change after the first phase has landed and its regression
suite is stable.

1. Persist session state first, with the existing failure and timeout policy.
2. Run chat update, MCP cleanup, and skill-detector shutdown concurrently in
   a `TaskGroup`.
3. Apply one shared cleanup deadline to those concurrent operations; cancel
   outstanding work at expiry and log outcomes according to the existing
   best-effort policy.
4. Add duration, deadline-hit, and per-operation failure metrics, and validate
   P95/P99 behavior with a targeted load test before rollout.

Session persistence remains serial because it is the highest-priority
consistency boundary. The other three cleanup operations have no known data
dependency on each other.

## Delivery Order

1. Implement test topology and fail-closed Python 3.12 CI gates.
2. Add query-flow characterization tests.
3. Extract first-phase private collaborators incrementally, preserving the
   established facade and event contracts.
4. Verify the full affected suite and critical runtime-path tests.
5. Implement cleanup parallelism as its own change, with metrics and load
   verification.
