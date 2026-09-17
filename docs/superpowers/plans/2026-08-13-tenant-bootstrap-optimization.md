# Tenant Bootstrap Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify batch and request-driven tenant bootstrap semantics, expose an authoritative bootstrap outcome, and reduce bootstrap-path overhead without weakening source-template isolation.

**Architecture:** Keep `TenantWorkspacePool` as the sole bootstrap authority and retain the existing fail-closed requirement that a source template and its providers are explicitly provisioned before source traffic may create or repair a tenant. Replace the batch router's duplicate filesystem readiness pre-check with the outcome returned from `ensure_bootstrap`; bootstrap integrity remains strict in this change. Move only the synchronous recovery boundary off the event loop, while preserving the existing cross-process `AsyncFlock` and double-check pattern.

**Tech Stack:** Python 3.11, FastAPI, asyncio, Pydantic/dataclasses, pytest, pytest-asyncio, GitNexus.

---

## Scope and non-goals

- Keep `WORKING_DIR/default_<source>` plus `SECRET_DIR/default_<source>/providers` as a fail-closed prerequisite for source-scoped bootstrap.
- Do not make public/request traffic provision source templates.
- Do not weaken `inspect_bootstrap_readiness()` in this change; its blast radius is CRITICAL.
- Do not change batch's `user_name`/`bbk_id` quality gate. Document it as batch-specific policy.
- Treat bounded batch concurrency, readiness-profile splitting, registry TTL, and identity lookup caching as follow-up phases after observability baselines exist.

## Risk and acceptance criteria

GitNexus impact analysis on 2026-08-13 reports `TenantWorkspacePool.ensure_bootstrap` as **CRITICAL** (65 affected processes) and `inspect_bootstrap_readiness` as **CRITICAL** (65 affected processes). Change the `ensure_bootstrap` return contract only with the tests below; do not change readiness semantics in this plan.

Acceptance criteria:

1. Batch and ordinary request paths use the same source-template readiness decision.
2. Batch marks only an outcome of `already_ready` as `skipped`; a successful recover/create is `created`.
3. A missing source template/providers causes the same `TenantBootstrapUnavailable`/503 contract from both paths.
4. Bootstrap recovery's blocking filesystem work does not block unrelated event-loop work.
5. Existing source-template provisioning, tenant recovery, and skill-sync tests remain green.

## File map

| File | Change |
| --- | --- |
| `src/swe/app/workspace/tenant_pool.py` | Add immutable bootstrap outcome, return it from `ensure_bootstrap`, remove unused local lock map, and offload synchronous recovery. |
| `src/swe/app/routers/internal.py` | Delete router-owned readiness check; map pool outcome to async-task `skipped`/`created`. |
| `tests/unit/app/test_tenant_pool.py` | Assert outcome semantics, source-template behavior, and event-loop responsiveness. |
| `tests/unit/routers/test_internal_tenant_scope.py` | Assert batch uses outcome semantics and does not maintain a second readiness predicate. |
| `tests/unit/workspace/test_source_template_provisioner.py` | Preserve/extend provider-directory prerequisite regression coverage if not already explicit. |
| `wiki/tenant-workspace-initialization/README.md` | Document the unified result contract and operations runbook. |

### Task 1: Define the authoritative bootstrap result

**Files:**
- Modify: `src/swe/app/workspace/tenant_pool.py:40-100, 327-558`
- Test: `tests/unit/app/test_tenant_pool.py`

- [ ] **Step 1: Add outcome tests before changing the pool API.**

Add test cases using the existing ready-tenant fixture/helpers in `tests/unit/app/test_tenant_pool.py`:

```python
@pytest.mark.asyncio
async def test_ensure_bootstrap_returns_already_ready_for_strict_ready_tenant(
    ready_pool: TenantWorkspacePool,
) -> None:
    result = await ready_pool.ensure_bootstrap("tenant-a")

    assert result.status == "already_ready"
    assert result.tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_ensure_bootstrap_returns_bootstrapped_after_recovery(
    pool: TenantWorkspacePool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        TenantInitializer,
        "recover_seeded_bootstrap",
        lambda self, **kwargs: {"recovered_paths": []},
    )
    monkeypatch.setattr(
        TenantInitializer,
        "has_seeded_bootstrap",
        lambda self: False,
    )

    result = await pool.ensure_bootstrap("tenant-a")

    assert result.status == "bootstrapped"
    assert result.tenant_id == "tenant-a"
```

- [ ] **Step 2: Run the new outcome tests and verify failure.**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py -k 'returns_already_ready or returns_bootstrapped' -q`

Expected: FAIL because `ensure_bootstrap()` returns `None`.

- [ ] **Step 3: Add an immutable outcome type and return it on every success path.**

At module level in `tenant_pool.py`, add:

```python
@dataclass(frozen=True)
class BootstrapOutcome:
    tenant_id: str
    status: Literal["already_ready", "bootstrapped"]
    duration_ms: int
```

Change `ensure_bootstrap(...) -> BootstrapOutcome`. On both fast paths, return `BootstrapOutcome(tenant_id=bootstrap_tenant_id, status="already_ready", duration_ms=duration_ms)`. After `_perform_bootstrap(...)`, return the same object with `status="bootstrapped"`. Do not return an outcome on lock or source-template failure; retain the existing exception/503 behavior.

- [ ] **Step 4: Run focused pool tests.**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the outcome contract.**

```bash
git add src/swe/app/workspace/tenant_pool.py tests/unit/app/test_tenant_pool.py
git commit -m "refactor(workspace): return tenant bootstrap outcome"
```

### Task 2: Make batch initialization consume the pool result

**Files:**
- Modify: `src/swe/app/routers/internal.py:603-621, 752-904`
- Test: `tests/unit/routers/test_internal_tenant_scope.py:957-1145`

- [ ] **Step 1: Replace router-owned readiness tests with outcome tests.**

Delete tests that monkeypatch `_is_tenant_already_bootstrapped`. Add a fake pool that returns the authoritative result:

```python
class OutcomePool:
    def __init__(self, status: Literal["already_ready", "bootstrapped"]) -> None:
        self.status = status
        self.calls: list[dict[str, object]] = []

    async def ensure_bootstrap(self, tenant_id: str, **kwargs) -> BootstrapOutcome:
        self.calls.append({"tenant_id": tenant_id, **kwargs})
        return BootstrapOutcome(
            tenant_id=tenant_id,
            status=self.status,
            duration_ms=1,
        )
class CapturingStore:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []
        self.finished: dict[str, object] | None = None

    async def mark_running(self, task_id: str) -> None:
        assert task_id == "task-1"

    async def record_item_result(self, **kwargs: object) -> None:
        self.items.append(kwargs)

    async def finish_task(self, **kwargs: object) -> None:
        self.finished = kwargs


@pytest.mark.parametrize(
    ("outcome_status", "expected_status"),
    [("already_ready", "skipped"), ("bootstrapped", "created")],
)
def test_batch_maps_authoritative_bootstrap_outcome(
    monkeypatch: pytest.MonkeyPatch,
    outcome_status: Literal["already_ready", "bootstrapped"],
    expected_status: Literal["skipped", "created"],
) -> None:
    async def fake_resolve_user_identity(**kwargs: object) -> ResolvedIdentity:
        return ResolvedIdentity(user_name="name-111", bbk_id="bbk-111")

    monkeypatch.setattr(internal_router, "resolve_user_identity", fake_resolve_user_identity)
    store = CapturingStore()
    pool = OutcomePool(outcome_status)
    payload = InternalBatchInitializeTenantsRequest(
        tenant_ids="111", source_id="RMASSIST",
    )

    asyncio.run(internal_router._run_internal_batch_initialize_task(
        task_id="task-1", store=store, pool=pool, payload=payload,
        tenant_ids=["111"], headers={},
    ))

    assert len(pool.calls) == 1
    assert store.items[0]["item_status"] == expected_status
    assert store.items[0]["result"]["status"] == expected_status
```

- [ ] **Step 2: Run the new router tests and verify failure.**

Run: `venv/bin/python -m pytest tests/unit/routers/test_internal_tenant_scope.py -k 'authoritative_ready_outcome or bootstrapped_outcome' -q`

Expected: FAIL because the worker checks `_is_tenant_already_bootstrapped` before calling the pool.

- [ ] **Step 3: Delete `_is_tenant_already_bootstrapped()` and map result status.**

In `_run_internal_batch_initialize_task`, always call:

```python
outcome = await pool.ensure_bootstrap(
    tenant_id,
    source_id=payload.source_id,
    tenant_name=resolved_identity.user_name,
    bbk_id=resolved_identity.bbk_id,
    enable_bootstrap_chat=payload.enable_bootstrap_chat,
)
item_status = (
    "skipped" if outcome.status == "already_ready" else "created"
)
```

Use `item_status` for both `record_item_result(item_status=...)` and `result["status"]`/`result["message"]`. Do not catch `SourceTemplateUnavailable` separately; the existing broad worker failure path must record it as one failed item, matching ordinary request semantics.

- [ ] **Step 4: Add the default-source providers regression test.**

Add this test alongside the pool source-template tests. It exercises the pool's authoritative decision and is the prerequisite for batch behavior:

```python
@pytest.mark.asyncio
async def test_source_default_is_not_ready_without_template_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "ruice"
    pool = TenantWorkspacePool(tmp_path)
    monkeypatch.setattr(tenant_pool_module, "SECRET_DIR", tmp_path / "secret")
    _write_strict_ready_tenant(tmp_path / f"default_{source_id}")

    with pytest.raises(SourceTemplateUnavailable):
        await pool.ensure_bootstrap("default", source_id=source_id)
```

In the router outcome test, use an `OutcomePool` replacement whose `ensure_bootstrap()` raises `SourceTemplateUnavailable`; assert `store.items[0]["item_status"] == "failed"`. This verifies the worker does not convert a source-template failure into `skipped`.

- [ ] **Step 5: Run router and source-template regressions.**

Run: `venv/bin/python -m pytest tests/unit/routers/test_internal_tenant_scope.py tests/unit/app/test_tenant_pool.py tests/unit/workspace/test_source_template_provisioner.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the batch unification.**

```bash
git add src/swe/app/routers/internal.py tests/unit/routers/test_internal_tenant_scope.py tests/unit/workspace/test_source_template_provisioner.py
git commit -m "fix(internal): unify batch tenant bootstrap readiness"
```

### Task 3: Remove unused in-process lock state and offload recovery I/O

**Files:**
- Modify: `src/swe/app/workspace/tenant_pool.py:87-94, 146-161, 365-371, 478-486`
- Test: `tests/unit/app/test_tenant_pool.py`

- [ ] **Step 1: Add event-loop responsiveness test.**

```python
@pytest.mark.asyncio
async def test_bootstrap_recovery_yields_to_other_event_loop_work(
    pool: TenantWorkspacePool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def blocking_recovery(self, **kwargs):
        started.set()
        assert release.wait(timeout=1)
        return {"recovered_paths": []}

    monkeypatch.setattr(TenantInitializer, "recover_seeded_bootstrap", blocking_recovery)
    bootstrap_task = asyncio.create_task(pool.ensure_bootstrap("tenant-a"))
    await asyncio.wait_for(asyncio.to_thread(started.wait, 1), timeout=1)
    tick = asyncio.create_task(asyncio.sleep(0))
    await asyncio.wait_for(tick, timeout=0.1)
    release.set()
    await bootstrap_task
```

- [ ] **Step 2: Run the responsiveness test and verify failure.**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py -k 'recovery_yields' -q`

Expected: FAIL or time out because `recover_seeded_bootstrap()` currently executes on the event loop.

- [ ] **Step 3: Remove unused local lock data and offload only the synchronous recovery call.**

Delete `self._bootstrap_locks`, `_get_or_create_bootstrap_lock()`, and the unused local `bootstrap_lock` assignment. In `_perform_bootstrap`, replace the direct call with:

```python
recovery_result = await asyncio.to_thread(
    initializer.recover_seeded_bootstrap,
    enable_bootstrap_chat=enable_bootstrap_chat,
)
```

Keep `AsyncFlock` and the re-check inside its context exactly as they are. The `flock` remains the cross-pod concurrency primitive.

- [ ] **Step 4: Run concurrency, lock, and focused workspace tests.**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py tests/unit/workspace/test_bootstrap_lock.py tests/unit/workspace/test_tenant_initializer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit I/O and lock cleanup.**

```bash
git add src/swe/app/workspace/tenant_pool.py tests/unit/app/test_tenant_pool.py
git commit -m "perf(workspace): offload tenant bootstrap recovery"
```

### Task 4: Observability and documentation

**Files:**
- Modify: `src/swe/app/workspace/tenant_pool.py:463-558`
- Modify: `wiki/tenant-workspace-initialization/README.md`
- Test: `tests/unit/app/test_tenant_pool.py`

- [ ] **Step 1: Add structured log assertions around outcome and failure reason.**

```python
@pytest.mark.asyncio
async def test_bootstrap_fast_path_emits_authoritative_outcome_log(
    ready_pool: TenantWorkspacePool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        result = await ready_pool.ensure_bootstrap("tenant-a")

    assert result.status == "already_ready"
    assert "tenant_bootstrap_outcome tenant_id=tenant-a outcome=already_ready" in caplog.text
```

Keep the existing source-template test and assert its captured log includes `tenant_bootstrap_source_template_not_ready` and `reason=missing_providers`.

- [ ] **Step 2: Run the log tests and verify failure.**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py -k 'bootstrap_outcome_log or source_template_not_ready_log' -q`

Expected: FAIL until the success outcome event is added.

- [ ] **Step 3: Emit one stable success event and update the runbook.**

Emit once per successful `ensure_bootstrap()` return:

```python
logger.info(
    "tenant_bootstrap_outcome tenant_id=%s outcome=%s duration_ms=%d",
    result.tenant_id,
    result.status,
    result.duration_ms,
)
```

Update the wiki to state: batch records `skipped` only for `already_ready`; `created` means the pool performed bootstrap/recovery; source-template 503 must be remediated through the internal source-template ensure endpoint.

- [ ] **Step 4: Run documentation and log checks.**

Run: `git diff --check && venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py -k 'bootstrap_outcome_log or source_template_not_ready_log' -q`

Expected: no whitespace errors and PASS.

- [ ] **Step 5: Commit observability and docs.**

```bash
git add src/swe/app/workspace/tenant_pool.py tests/unit/app/test_tenant_pool.py wiki/tenant-workspace-initialization/README.md
git commit -m "docs(workspace): document tenant bootstrap outcomes"
```

### Task 5: Full verification and change-scope review

**Files:**
- Verify only; no source changes.

- [ ] **Step 1: Run the complete focused regression suite.**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py tests/unit/app/test_tenant_workspace.py tests/unit/workspace/test_bootstrap_state.py tests/unit/workspace/test_bootstrap_lock.py tests/unit/workspace/test_source_template_provisioner.py tests/unit/workspace/test_tenant_initializer.py tests/unit/routers/test_internal_tenant_scope.py tests/integrated/test_bootstrap_with_skill_sync.py -q`

Expected: PASS.

- [ ] **Step 2: Run formatting/static hooks for changed files.**

Run: `venv/bin/python -m pre_commit run --files src/swe/app/workspace/tenant_pool.py src/swe/app/routers/internal.py tests/unit/app/test_tenant_pool.py tests/unit/routers/test_internal_tenant_scope.py wiki/tenant-workspace-initialization/README.md`

Expected: PASS.

- [ ] **Step 3: Review scope with GitNexus before final commit or PR.**

Run `detect_changes({"repo":"CoPaw","scope":"all"})`; inspect every changed symbol and affected process. If `ensure_bootstrap` or readiness changes reach routes outside the planned files, stop and investigate before publishing.

- [ ] **Step 4: Update the plan status and hand off.**

Record test commands/results in the PR description or implementation handoff. State explicitly that source-template provisioning remains privileged and request traffic remains fail-closed.

## Follow-up phases (not included in this implementation)

1. **Readiness profiles:** introduce `bootstrap_integrity` and `runtime_liveness` only after a product decision defines whether missing optional prompt/state artifacts should be healed, ignored, or reported. This must not silently re-create user-deleted files.
2. **Bounded batch concurrency:** add a payload/configured concurrency cap after measuring identity service capacity; preserve one task result per requested tenant and rely on `AsyncFlock` for same-tenant serialization.
3. **Registry/identity cache governance:** add tenant-entry TTL/LRU and a short identity cache only with metrics for cardinality, eviction, remote lookup latency, and error rate.
