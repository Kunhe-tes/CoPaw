# System Runtime Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit periodic per-Pod runtime diagnostic logs covering SSE concurrency, event-loop lag, current Python process resources, and `/opt/deployments/app` filesystem usage.

**Architecture:** Add an isolated `RuntimeDiagnosticManager` that owns metric windows, process/storage collection, lifecycle logging, and periodic sampling. Add a pure ASGI SSE middleware that updates the manager's connection counters, then wire both into the existing FastAPI application lifespan without changing the existing liveness endpoint.

**Tech Stack:** Python, asyncio, FastAPI/Starlette ASGI, psutil, pytest/pytest-asyncio

---

### Task 1: Diagnostic Metric Windows And Log Contract

**Files:**
- Create: `src/swe/app/runtime_diagnostic.py`
- Create: `tests/unit/app/test_runtime_diagnostic.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing tests for lifecycle and metric payloads**

Add tests that instantiate `RuntimeDiagnosticManager` with a fixed hostname,
clock, process collector, disk collector, and log sink. Verify:

- registration and deregistration payloads use `runtime_diagnostic.v1`,
  `event_at_ms`, and flat fields;
- a diagnostic flow contains the confirmed metric fields;
- failed process or storage reads produce `null` fields without suppressing the
  event;
- window rotation preserves active SSE count, resets SSE peak to active count,
  and clears event-loop and CPU samples.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_runtime_diagnostic.py -v
```

Expected: collection fails because `swe.app.runtime_diagnostic` does not exist.

- [ ] **Step 3: Implement the metric manager and add psutil**

Create focused types in `runtime_diagnostic.py`:

```python
class RuntimeDiagnosticManager:
    def record_sse_opened(self) -> None: ...
    def record_sse_closed(self) -> None: ...
    def record_sample(self, lag_ms: float, cpu_percent: float | None) -> None: ...
    def build_diagnostic_payload(self) -> dict[str, object]: ...
    def emit_registered(self) -> None: ...
    def emit_diagnostic(self) -> None: ...
    def emit_deregistered(self) -> None: ...
```

Use compact JSON after the fixed `RUNTIME_DIAGNOSTIC ` prefix. Use
`psutil.Process()` for CPU, memory, threads, file descriptors, and uptime, and
`psutil.disk_usage("/opt/deployments/app")` for storage. Add `psutil>=5.9.0` to
project dependencies.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_runtime_diagnostic.py -v
```

Expected: all manager and payload tests pass.

### Task 2: Periodic Sampler And Lifecycle

**Files:**
- Modify: `src/swe/app/runtime_diagnostic.py`
- Modify: `tests/unit/app/test_runtime_diagnostic.py`

- [ ] **Step 1: Write failing async lifecycle tests**

Add tests that verify:

- `start()` emits registration immediately;
- the sampler records event-loop lag and process CPU every second;
- the first diagnostic waits 120 seconds plus bounded 0-10 second jitter;
- later diagnostics run every 1800 seconds;
- collection errors do not terminate the loop;
- `stop()` cancels tasks and emits deregistration.

- [ ] **Step 2: Run lifecycle tests to verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_runtime_diagnostic.py -v
```

Expected: lifecycle tests fail because `start()` and `stop()` are absent.

- [ ] **Step 3: Implement periodic sampling**

Use separate asyncio tasks for the one-second sampler and periodic emitter.
Measure lag from planned monotonic wake-up time, prime process CPU sampling
before the first accepted sample, catch non-cancellation exceptions, and await
task cancellation during shutdown.

- [ ] **Step 4: Run lifecycle tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_runtime_diagnostic.py -v
```

Expected: all runtime diagnostic tests pass.

### Task 3: SSE ASGI Instrumentation

**Files:**
- Create: `src/swe/app/middleware/sse_diagnostic.py`
- Create: `tests/unit/app/test_sse_diagnostic_middleware.py`

- [ ] **Step 1: Write failing SSE middleware tests**

Build small ASGI applications and verify:

- `text/event-stream` increments active count and updates peak;
- the active count decrements exactly once after normal completion;
- exceptions and disconnects decrement exactly once;
- ordinary responses and non-SSE streaming responses are ignored.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_sse_diagnostic_middleware.py -v
```

Expected: collection fails because the middleware module does not exist.

- [ ] **Step 3: Implement pure ASGI middleware**

Wrap the ASGI `send` callable, inspect `http.response.start` headers for
`text/event-stream`, increment once, and decrement in `finally`. Do not use
`BaseHTTPMiddleware`, because it does not reliably represent the full
streaming response lifecycle.

- [ ] **Step 4: Run middleware tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_sse_diagnostic_middleware.py -v
```

Expected: all SSE middleware tests pass.

### Task 4: FastAPI Application Integration

**Files:**
- Modify: `src/swe/app/_app.py`
- Modify: `tests/unit/app/test_runtime_diagnostic_integration.py`

- [ ] **Step 1: Write failing integration tests**

Verify:

- the FastAPI app has one shared diagnostic manager;
- lifespan starts and stops that manager;
- the SSE middleware receives the same manager;
- `/api/health/health` remains unchanged.

- [ ] **Step 2: Run integration tests to verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_runtime_diagnostic_integration.py -v
```

Expected: tests fail because the manager is not wired into the app.

- [ ] **Step 3: Wire manager and middleware**

Create one process-local manager during app construction, register
`SSEDiagnosticMiddleware`, call `start()` after normal application startup,
and call `stop()` at the beginning of graceful shutdown so deregistration is
emitted before other shutdown work.

- [ ] **Step 4: Run integration and regression tests**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/app/test_runtime_diagnostic.py \
  tests/unit/app/test_sse_diagnostic_middleware.py \
  tests/unit/app/test_runtime_diagnostic_integration.py \
  tests/unit/app/test_health_route.py \
  tests/unit/app/test_lazy_loading.py -v
```

Expected: all selected tests pass.

### Task 5: Operational Documentation And Final Verification

**Files:**
- Modify: `analysis/playbook/log-entrypoints.md`
- Modify: `analysis/observability-and-supporting-systems.md`

- [ ] **Step 1: Document the runtime diagnostic log entrypoint**

Document the `RUNTIME_DIAGNOSTIC ` prefix, three event types, metric scope,
`HOSTNAME` identity, 75-minute downstream lease, and 30-day flow retention.

- [ ] **Step 2: Run formatting and focused tests**

Run:

```bash
git diff --check
venv/bin/python -m pytest \
  tests/unit/app/test_runtime_diagnostic.py \
  tests/unit/app/test_sse_diagnostic_middleware.py \
  tests/unit/app/test_runtime_diagnostic_integration.py \
  tests/unit/app/test_health_route.py \
  tests/unit/app/test_lazy_loading.py -v
```

Expected: no formatting errors and all selected tests pass.

- [ ] **Step 3: Run broader unit regression suite**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/ -v
```

Expected: all application unit tests pass.

- [ ] **Step 4: Review affected scope**

Run GitNexus staged or all-change detection and verify only runtime diagnostic,
FastAPI lifecycle, middleware, dependency, tests, and operational docs are
affected.

