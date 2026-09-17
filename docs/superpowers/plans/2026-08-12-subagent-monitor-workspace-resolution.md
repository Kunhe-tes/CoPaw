# SubAgent Monitor Workspace Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the SubAgent monitor APIs resolve the complete agent Workspace so active runs can reach the existing Console progress control.

**Architecture:** Replace the router-local workspace dependency with the existing `swe.app.runner.api.get_workspace` dependency. The standard dependency delegates to `get_agent_for_request`, which ignores the lightweight tenant middleware context and obtains the complete agent-scoped Workspace. Keep both endpoint paths and response schemas unchanged.

**Tech Stack:** FastAPI dependency injection, Python 3, pytest/TestClient, existing SubAgent monitor service.

---

## File Structure

- Modify: `src/swe/app/routers/subagents.py` — consume the standard complete-Workspace dependency instead of returning `request.state.workspace` directly.
- Modify: `tests/unit/subagents/test_monitor_api.py` — inject the standard dependency in router tests and add the regression scenario where middleware puts a lightweight context on the request.
- No frontend, API-schema, or persistence changes.

### Task 1: Lock down the lightweight-context regression

**Files:**
- Modify: `tests/unit/subagents/test_monitor_api.py:9-96`

- [ ] **Step 1: Import the real route dependency and lightweight context type**

```python
from swe.app.middleware.tenant_workspace import TenantWorkspaceContext
from swe.app.runner.api import get_workspace
```

Keep the existing `router` import. These imports let the test inject the exact dependency that production chat routes use and construct the context that caused the production failure.

- [ ] **Step 2: Change `_client` to inject the standard dependency while retaining the legacy app-state fixture**

```python
def _client(
    tmp_path,
    *,
    request_workspace: object | None = None,
) -> tuple[TestClient, PerRunSubAgentRunStore, _Supervisor]:
    app = FastAPI()
    app.include_router(router)
    store = PerRunSubAgentRunStore(tmp_path / "subagent_runs")
    supervisor = _Supervisor(store)
    workspace = SimpleNamespace(
        agent_id="agent-1",
        tenant_id="tenant-1",
        workspace_dir=tmp_path,
        chat_manager=_ChatManager(),
        config=AgentProfileConfig(
            id="agent-1",
            name="Agent",
            workspace_dir=str(tmp_path),
        ),
        subagent_supervisor=supervisor,
        subagent_run_store_dir=tmp_path / "subagent_runs",
    )
    app.state.workspace = workspace
    app.dependency_overrides[get_workspace] = lambda: workspace
    if request_workspace is not None:

        @app.middleware("http")
        async def inject_workspace_context(request, call_next):
            request.state.workspace = request_workspace
            return await call_next(request)

    return TestClient(app), store, supervisor
```

The app-state value preserves existing test behavior until the implementation lands. The explicit dependency override makes every route test assert that it uses `runner.api.get_workspace`; the optional middleware simulates the production context.

- [ ] **Step 3: Add the failing GET regression test immediately before `test_snapshot_returns_slim_current_chat_runs`**

```python
def test_monitor_snapshot_ignores_lightweight_request_workspace(tmp_path) -> None:
    client, store, _supervisor = _client(
        tmp_path,
        request_workspace=TenantWorkspaceContext("tenant-1", tmp_path),
    )

    import asyncio

    asyncio.run(
        _create_run(
            store,
            run_id="subagent-running",
            session_id="session-1",
            status="running",
        ),
    )

    response = client.get("/subagents/runs", params={"chat_id": "chat-1"})

    assert response.status_code == 200
    assert [item["run_id"] for item in response.json()["runs"]] == [
        "subagent-running",
    ]
```

The old local dependency sees the injected `TenantWorkspaceContext`, cannot find `chat_manager`, and makes this test fail with HTTP 500. The fixed endpoint receives the dependency-overridden complete workspace and returns the run.

- [ ] **Step 4: Run the regression test and confirm the pre-fix failure**

Run:

```bash
../../venv/bin/python -m pytest \
  tests/unit/subagents/test_monitor_api.py::test_monitor_snapshot_ignores_lightweight_request_workspace \
  -q
```

Expected: FAIL because the response status is `500`, with `ChatManager not initialized`.

- [ ] **Step 5: Commit the failing regression test**

```bash
git add tests/unit/subagents/test_monitor_api.py
git commit -m "test(subagents): cover lightweight workspace monitor request"
```

### Task 2: Reuse the standard Workspace dependency

**Files:**
- Modify: `src/swe/app/routers/subagents.py:8-39`

- [ ] **Step 1: Replace the local resolver imports and helper**

Replace:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..agent_context import get_agent_for_request
```

with:

```python
from fastapi import APIRouter, Depends, HTTPException, Query

from ..runner.api import get_workspace
```

Delete the complete `_get_workspace` function. Keep `_get_chat` and `_monitor_service` unchanged.

- [ ] **Step 2: Point both endpoints at the standard dependency**

Replace both dependency declarations:

```python
workspace: Any = Depends(_get_workspace),
```

with:

```python
workspace: Any = Depends(get_workspace),
```

This changes only dependency resolution; `chat_id`, cancellation payloads, status codes, and response models remain untouched.

- [ ] **Step 3: Run the targeted router suite**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/subagents/test_monitor_api.py -q
```

Expected: PASS, including the new lightweight-context test and all existing snapshot/cancellation cases.

- [ ] **Step 4: Run static checks on modified Python files**

Run:

```bash
../../venv/bin/python -m black --check \
  src/swe/app/routers/subagents.py \
  tests/unit/subagents/test_monitor_api.py
../../venv/bin/python -m pylint \
  src/swe/app/routers/subagents.py \
  tests/unit/subagents/test_monitor_api.py
```

Expected: both commands exit 0. If repository-wide lint is known to fail, do not substitute it for these file-scoped checks.

- [ ] **Step 5: Review scope and commit the implementation**

Run GitNexus `detect_changes()` for the worktree and confirm only the router dependency wiring and monitor API tests changed. Then run:

```bash
git add src/swe/app/routers/subagents.py tests/unit/subagents/test_monitor_api.py
git commit -m "fix(subagents): resolve monitor workspace through agent context"
```

### Task 3: Verify the user-visible path

**Files:**
- Verify only; no source changes.

- [ ] **Step 1: Start the application with the repaired backend and current Console source**

Use the project’s normal backend command and the Console development server from `console/`:

```bash
pnpm dev
```

- [ ] **Step 2: Start a Background SubAgent in an existing chat and inspect the monitor request**

Verify in the browser Network panel:

```text
GET /api/subagents/runs?chat_id=<existing-chat-uuid> -> 200
```

The response must contain the same `chat_id`, its logical `session_id`, and a non-empty `runs` array while the Background SubAgent is active.

- [ ] **Step 3: Verify monitor UI behavior**

Confirm the existing floating trigger appears at the right side above the composer, expands to show status/progress, and the stop action keeps its existing API call. This validates the original symptom without changing Console code.
