# Background SubAgent Subprocess Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the synchronous SubAgent tool surface with background-only subprocess-backed SubAgent tools that can start, wait, get, and cancel runs.

**Architecture:** Add a per-run JSON store, a subprocess launch spec, a main-process supervisor, an internal worker module, and four Main Agent tools: `start_subagent`, `wait_subagent`, `get_subagent`, and `cancel_subagent`. Keep the existing readonly SubAgent runtime and policy enforcement, but remove `delegate_to_subagent` from the Main Agent toolkit.

**Tech Stack:** Python 3.12, Pydantic, asyncio-compatible tool functions, `subprocess.Popen`, POSIX process groups, pytest.

---

## File Map

- Modify `src/swe/app/subagents/models.py`
  - Add background run lifecycle status, worker metadata, launch spec, compact result view models, and `start_subagent` response models.
- Modify `src/swe/app/subagents/run_store.py`
  - Add `PerRunSubAgentRunStore` while leaving the old stores available for compatibility tests until removal is safe.
- Create `src/swe/app/subagents/supervisor.py`
  - Main-process supervisor for active subprocess handles, concurrency limits, lazy reap, and cancellation.
- Create `src/swe/app/subagents/worker.py`
  - Internal `python -m swe.app.subagents.worker --launch-spec <path>` entrypoint.
- Create `src/swe/agents/tools/subagent_background.py`
  - Tool factory for `start_subagent`, `wait_subagent`, `get_subagent`, and `cancel_subagent`.
- Modify `src/swe/app/subagents/__init__.py`
  - Export new models, store, supervisor, and tool helpers where appropriate.
- Modify `src/swe/agents/react_agent.py`
  - Register background SubAgent tools under the approved visibility rules and stop registering `delegate_to_subagent`.
- Modify `src/swe/agents/tool_guard_mixin.py`
  - Update any hard-coded SubAgent delegation references if needed after removing synchronous delegation visibility.
- Modify tests under `tests/unit/subagents/`
  - Add store, supervisor, worker, tool, and toolkit visibility coverage.

## Task 1: Background Run Models And Per-Run Store

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/run_store.py`
- Modify: `src/swe/app/subagents/__init__.py`
- Test: `tests/unit/subagents/test_background_run_store.py`

- [ ] **Step 1: Write failing tests for lifecycle statuses and per-run files**

Add `tests/unit/subagents/test_background_run_store.py` with tests that assert:

```python
@pytest.mark.asyncio
async def test_per_run_store_writes_one_file_per_run(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)
    record = await store.create(spec, definition, PermissionPolicy.readonly())
    assert (tmp_path / f"{record.run_id}.json").exists()
    assert not (tmp_path / "subagent_runs.json").exists()

@pytest.mark.asyncio
async def test_per_run_store_terminal_state_is_first_writer_wins(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)
    record = await store.create(spec, definition, PermissionPolicy.readonly())
    completed = await store.finish(record.run_id, completed_result)
    cancelled = await store.cancel(record.run_id)
    assert cancelled.status == completed.status == "completed"
    assert cancelled.result == completed_result

@pytest.mark.asyncio
async def test_per_run_store_marks_running_with_worker_metadata(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)
    record = await store.create(spec, definition, PermissionPolicy.readonly())
    running = await store.mark_running(record.run_id, worker_pid=123)
    assert running.status == "running"
    assert running.worker.pid == 123
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_run_store.py -v
```

Expected: import errors for `PerRunSubAgentRunStore` and missing background model fields.

- [ ] **Step 3: Implement background models and store**

Implement:

- `BackgroundRunStatus = Literal["pending", "running", "paused", "completed", "failed", "cancelled", "expired"]`
- `TERMINAL_BACKGROUND_RUN_STATUSES`
- `WorkerProcessInfo`
- `WorkerLaunchSpec`
- `BackgroundSubAgentRunRecord`
- `PerRunSubAgentRunStore`

Store behavior:

- `create()` writes `<run_id>.json` with status `pending`.
- `mark_running(run_id, worker_pid=...)` updates worker metadata and status.
- `finish()` maps any valid `AgentResult` terminal outcome to lifecycle `completed`.
- `fail()` writes lifecycle `failed`.
- `cancel()` writes lifecycle `cancelled`.
- terminal writes are first-writer-wins.
- writes use temp file plus `Path.replace()`.

- [ ] **Step 4: Verify store tests pass**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_run_store.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/swe/app/subagents/models.py src/swe/app/subagents/run_store.py src/swe/app/subagents/__init__.py tests/unit/subagents/test_background_run_store.py
git commit -m "feat(subagents): add per-run background store"
```

## Task 2: Worker Entrypoint

**Files:**
- Create: `src/swe/app/subagents/worker.py`
- Modify: `src/swe/app/subagents/__init__.py`
- Test: `tests/unit/subagents/test_background_worker.py`

- [ ] **Step 1: Write failing worker tests**

Add tests that:

```python
def test_launch_spec_rejects_secret_like_context(tmp_path):
    spec = WorkerLaunchSpec.model_validate({...})
    assert "OPENAI_API_KEY" not in spec.model_dump_json()

@pytest.mark.asyncio
async def test_worker_writes_terminal_result_from_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(worker_module, "SubAgentRuntime", FakeRuntime)
    exit_code = await worker_module.run_worker(launch_spec_path)
    record = await PerRunSubAgentRunStore(run_store_dir).get(run_id)
    assert record.status == "completed"

@pytest.mark.asyncio
async def test_worker_exception_writes_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(worker_module, "SubAgentRuntime", RaisingRuntime)
    exit_code = await worker_module.run_worker(launch_spec_path)
    record = await PerRunSubAgentRunStore(run_store_dir).get(run_id)
    assert record.status == "failed"
```

- [ ] **Step 2: Verify worker tests fail**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_worker.py -v
```

Expected: missing worker module / run function.

- [ ] **Step 3: Implement `worker.py`**

Implement:

- `load_launch_spec(path: Path) -> WorkerLaunchSpec`
- `async run_worker(path: Path) -> int`
- `main(argv: list[str] | None = None) -> int`
- `if __name__ == "__main__": raise SystemExit(main())`

Worker must:

- load launch spec,
- create `PerRunSubAgentRunStore`,
- mark run running if needed,
- call `SubAgentRuntime.run()`,
- write failed state on unexpected exception,
- avoid printing protocol JSON to stdout.

- [ ] **Step 4: Verify worker tests pass**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_worker.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/swe/app/subagents/worker.py src/swe/app/subagents/__init__.py tests/unit/subagents/test_background_worker.py
git commit -m "feat(subagents): add subprocess worker entrypoint"
```

## Task 3: Supervisor

**Files:**
- Create: `src/swe/app/subagents/supervisor.py`
- Modify: `src/swe/app/subagents/__init__.py`
- Test: `tests/unit/subagents/test_background_supervisor.py`

- [ ] **Step 1: Write failing supervisor tests**

Add tests for:

```python
@pytest.mark.asyncio
async def test_start_blocks_when_concurrency_limit_reached(tmp_path):
    supervisor = BackgroundSubAgentSupervisor(max_running_per_scope=1, ...)
    first = await supervisor.start(...)
    second = await supervisor.start(...)
    assert second.status == "blocked"
    assert second.reason == "background_subagent_concurrency_limit"

@pytest.mark.asyncio
async def test_wait_lazy_reaps_worker_without_result(tmp_path):
    fake_process.returncode = 1
    snapshot = await supervisor.wait(scope, timeout_ms=1)
    assert snapshot.terminal_runs[0].status == "failed"

@pytest.mark.asyncio
async def test_cancel_terminates_process_group(tmp_path, monkeypatch):
    response = await supervisor.cancel(scope, run_id)
    assert response.status == "cancelled"
```

- [ ] **Step 2: Verify supervisor tests fail**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_supervisor.py -v
```

Expected: missing supervisor module.

- [ ] **Step 3: Implement supervisor**

Implement:

- `BackgroundSubAgentSupervisor`
- `BackgroundSubAgentScope`
- `BackgroundSubAgentStartBlocked`
- `start()`
- `wait()`
- `get()`
- `cancel()`
- lazy reap helper

Use `subprocess.Popen` with:

- `sys.executable`
- `-m swe.app.subagents.worker`
- `--launch-spec <path>`
- stderr redirected to the run stderr log path
- stdout redirected to `subprocess.DEVNULL`
- POSIX process group creation where available.

- [ ] **Step 4: Verify supervisor tests pass**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_supervisor.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/swe/app/subagents/supervisor.py src/swe/app/subagents/__init__.py tests/unit/subagents/test_background_supervisor.py
git commit -m "feat(subagents): supervise background subprocess runs"
```

## Task 4: Background Tools And Toolkit Visibility

**Files:**
- Create: `src/swe/agents/tools/subagent_background.py`
- Modify: `src/swe/agents/react_agent.py`
- Modify: `src/swe/agents/tools/__init__.py`
- Test: `tests/unit/subagents/test_background_tools.py`
- Test: `tests/unit/subagents/test_react_agent_and_guard_integration.py`

- [ ] **Step 1: Write failing tool tests**

Add tests that assert:

```python
async def test_start_subagent_returns_blocked_without_run_file_when_limit_reached(...):
    response = await start_subagent("plan-researcher", "Inspect")
    payload = json.loads(response.content[0]["text"])
    assert payload["status"] == "blocked"

def test_background_tools_visible_only_for_main_agent_with_subagent_intent(...):
    toolkit = SWEAgent._create_toolkit(agent_with_intent)
    assert "start_subagent" in toolkit.tools
    assert "delegate_to_subagent" not in toolkit.tools

def test_wait_tools_visible_with_active_background_runs(...):
    toolkit = SWEAgent._create_toolkit(agent_with_active_runs)
    assert "wait_subagent" in toolkit.tools
```

- [ ] **Step 2: Verify tool tests fail**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_react_agent_and_guard_integration.py -v
```

Expected: background tool imports missing or toolkit visibility assertions fail.

- [ ] **Step 3: Implement background tool factory**

Implement `create_background_subagent_tools(...)` returning callables for:

- `start_subagent`
- `wait_subagent`
- `get_subagent`
- `cancel_subagent`

Use supervisor from request context when provided, otherwise a module-level default supervisor.

Implement conservative intent detection in runner/request context plumbing or in toolkit context:

- current user text / metadata can set `subagent_tools_requested`.
- active supervisor handles allow observe/cancel tools.
- SubAgent contexts never see these tools.

Remove `delegate_to_subagent` registration from `SWEAgent._create_toolkit`.

- [ ] **Step 4: Verify tool tests pass**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_react_agent_and_guard_integration.py -v
```

Expected: all updated tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/swe/agents/tools/subagent_background.py src/swe/agents/react_agent.py src/swe/agents/tools/__init__.py tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_react_agent_and_guard_integration.py
git commit -m "feat(subagents): add background management tools"
```

## Task 5: Integration And Cleanup

**Files:**
- Modify: `tests/unit/subagents/test_runtime_and_delegation.py`
- Modify: `tests/unit/subagents/test_models_registry_policy.py`
- Modify: `src/swe/app/subagents/__init__.py`
- Optional delete: `src/swe/agents/tools/delegate_to_subagent.py` after all imports are removed.

- [ ] **Step 1: Update tests for removed synchronous tool**

Replace assertions that expect `delegate_to_subagent` with assertions that it is no longer registered as a Main Agent tool. Keep lower-level `DelegationManager` tests if still useful for runtime construction, or move the shared logic behind supervisor/tool tests.

- [ ] **Step 2: Run focused SubAgent suite**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents -v
```

Expected: all SubAgent tests pass.

- [ ] **Step 3: Run adjacent Plan Mode/tool guard tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_plan_mode_state.py tests/unit/app/test_task_progress_switch.py tests/unit/agents/tools/test_planning.py tests/unit/routers/test_console_chat_stream.py -v
```

Expected: all selected tests pass.

- [ ] **Step 4: Run GitNexus changed-scope review**

Run `gitnexus_detect_changes()` on staged changes. Expected risk should be understood and no unexpected unrelated symbols should appear.

- [ ] **Step 5: Final commit**

```bash
git add src/swe tests
git commit -m "feat(subagents): replace synchronous delegation with background runs"
```

## Review And Verification

- Run `venv/bin/python -m pytest tests/unit/subagents -v`.
- Run the adjacent Plan Mode/tool guard tests listed above.
- Run `gitnexus_detect_changes()` before each commit.
- Perform a code review pass focused on:
  - subprocess launch safety,
  - run store first-writer-wins,
  - scope isolation by `tenant_id + agent_id`,
  - no secret persistence in launch spec or run file,
  - `delegate_to_subagent` no longer visible as a Main Agent tool.

## Spec Coverage Check

- Subprocess backend: Tasks 2 and 3.
- Per-run JSON result source: Task 1.
- Fixed per-scope concurrency limit: Task 3.
- Process-group cancellation: Task 3.
- Background tools: Task 4.
- Tool visibility and intent gating: Task 4.
- Removal of synchronous Main Agent tool: Tasks 4 and 5.
- Tests and review: Task 5.
