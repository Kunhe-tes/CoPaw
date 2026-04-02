# Multi-Tenant Isolation Follow-up Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining strict multi-tenant isolation gaps by removing global fallbacks, scoping runtime/config/env behavior to tenant workspaces, and adding verification strong enough to justify completion claims.

**Architecture:** Keep the current tenant workspace model as the foundation, but tighten every remaining boundary where behavior is still app-global or silently falls back to global state. The remediation should proceed from the highest-risk shared-state leaks first, then converge on verification and documentation alignment once runtime behavior is actually isolated.

**Tech Stack:** FastAPI, contextvars, existing Workspace/ServiceManager runtime, Pydantic config models, APScheduler cron runtime, ReMeLight memory manager, pytest

---

## File Structure / Responsibility Map

### Runtime and routing
- `src/copaw/app/middleware/tenant_identity.py`
  - Enforce tenant identity requirements for non-exempt routes
- `src/copaw/app/_app.py`
  - Middleware registration and shared runtime initialization
- `src/copaw/app/agent_context.py`
  - Tenant-first agent/config/runtime resolution
- `src/copaw/app/routers/console.py`
  - Console APIs and push-message reads
- `src/copaw/app/console_push_store.py`
  - In-memory message isolation boundaries
- `src/copaw/app/routers/agents.py`
  - Tenant-local agent CRUD and workspace initialization

### Tenant-scoped storage and config helpers
- `src/copaw/envs/store.py`
  - Persistent env storage and current `os.environ` synchronization behavior
- `src/copaw/app/routers/envs.py`
  - Tenant env API behavior
- `src/copaw/config/utils.py`
  - Tenant path helpers and current non-strict fallbacks

### Background execution
- `src/copaw/app/crons/executor.py`
  - Cron execution context binding
- `src/copaw/app/crons/heartbeat.py`
  - Heartbeat file lookup and tenant-bound execution
- `src/copaw/app/workspace/workspace.py`
  - Workspace-local cron manager construction

### Verification
- `tests/unit/app/test_tenant_identity.py`
  - Tenant header and middleware behavior
- `tests/unit/app/test_tenant_workspace.py`
  - Middleware ordering and workspace binding evidence
- `tests/unit/app/test_tenant_middleware.py`
  - App initialization/runtime integration checks
- `tests/unit/app/test_console_push_store.py`
  - Push-store isolation semantics
- `tests/unit/routers/` new focused router tests
  - envs / console / workspace / agents isolation coverage
- `tests/unit/app/crons/` new focused cron tests
  - tenant-bound cron and heartbeat execution

---

## Scope split

This follow-up plan is intentionally focused on the remaining remediation work only. It excludes already-audited foundations such as tenant context primitives, tenant workspace pool creation, tenant-scoped settings pathing, and tenant-scoped workspace archive basics.

The work is grouped into five implementation units:
1. Stop shared-state leaks in env/runtime identity boundaries
2. Make agent/runtime resolution genuinely tenant-local
3. Tighten same-tenant session boundaries in console push behavior
4. Bind tenant workspace into all cron/heartbeat execution paths
5. Replace weak verification with evidence strong enough to support final documentation

---

### Task 1: Stop tenant env writes from mutating process-global `os.environ`

**Files:**
- Modify: `src/copaw/envs/store.py:182-245`
- Modify: `src/copaw/app/routers/envs.py:41-90`
- Test: `tests/unit/routers/test_envs_tenant_scope.py`

- [ ] **Step 1: Write the failing env isolation tests**

```python
from pathlib import Path

from copaw.envs.store import load_envs, save_envs


def test_save_envs_with_custom_path_does_not_mutate_process_env(tmp_path, monkeypatch):
    envs_path = tmp_path / "tenant-a" / ".secret" / "envs.json"
    monkeypatch.delenv("TENANT_ONLY_KEY", raising=False)

    save_envs({"TENANT_ONLY_KEY": "value-a"}, envs_path)

    assert load_envs(envs_path) == {"TENANT_ONLY_KEY": "value-a"}
    assert "TENANT_ONLY_KEY" not in __import__("os").environ


def test_delete_env_var_with_custom_path_does_not_remove_process_env(tmp_path, monkeypatch):
    envs_path = tmp_path / "tenant-a" / ".secret" / "envs.json"
    monkeypatch.setenv("TENANT_ONLY_KEY", "runtime")
    save_envs({"TENANT_ONLY_KEY": "tenant"}, envs_path)

    from copaw.envs.store import delete_env_var
    delete_env_var("TENANT_ONLY_KEY", envs_path)

    assert load_envs(envs_path) == {}
    assert __import__("os").environ["TENANT_ONLY_KEY"] == "runtime"
```

- [ ] **Step 2: Run the new failing tests**

Run:
```bash
pytest tests/unit/routers/test_envs_tenant_scope.py -k "custom_path or delete_env_var" -v
```

Expected:
- FAIL because custom-path tenant writes still flow through `_sync_environ(...)`

- [ ] **Step 3: Implement the minimal storage split**

Update `src/copaw/envs/store.py` so `save_envs()` only syncs `os.environ` when `path is None`, and custom-path tenant storage remains file-only.

```python
def save_envs(
    envs: dict[str, str],
    path: Optional[Path] = None,
) -> None:
    sync_process_env = path is None
    if path is None:
        path = get_envs_json_path()
        _migrate_legacy_envs_json(path)
    old = load_envs(path)
    if path.exists() and not path.is_file():
        raise IsADirectoryError(
            f"envs.json path exists but is not a regular file: {path}",
        )
    _prepare_secret_parent(path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(envs, fh, indent=2, ensure_ascii=False)
    _chmod_best_effort(path, 0o600)
    if sync_process_env:
        _sync_environ(old, envs)
```

- [ ] **Step 4: Add one router-level regression test**

```python
def test_tenant_env_api_is_file_scoped_not_process_scoped(client, monkeypatch):
    monkeypatch.delenv("TENANT_ONLY_KEY", raising=False)

    response = client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"TENANT_ONLY_KEY": "value-a"},
    )

    assert response.status_code == 200
    assert "TENANT_ONLY_KEY" not in __import__("os").environ
```

- [ ] **Step 5: Run the env tests again**

Run:
```bash
pytest tests/unit/routers/test_envs_tenant_scope.py -v
```

Expected:
- PASS for custom-path tenant env isolation coverage

- [ ] **Step 6: Commit**

```bash
git add tests/unit/routers/test_envs_tenant_scope.py src/copaw/envs/store.py src/copaw/app/routers/envs.py
git commit -m "fix(tenant): stop tenant env writes from mutating process env"
```

---

### Task 2: Enforce strict `X-Tenant-Id` behavior on non-exempt routes

**Files:**
- Modify: `src/copaw/app/middleware/tenant_identity.py:92-158`
- Modify: `src/copaw/app/_app.py:295-304`
- Test: `tests/unit/app/test_tenant_identity.py`

- [ ] **Step 1: Write the failing strict-header tests**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copaw.app.middleware.tenant_identity import TenantIdentityMiddleware


def build_test_app():
    app = FastAPI()
    app.add_middleware(
        TenantIdentityMiddleware,
        require_tenant=True,
        default_tenant_id=None,
    )

    @app.get("/api/settings")
    def stateful_route():
        return {"ok": True}

    @app.get("/api/version")
    def exempt_route():
        return {"version": "test"}

    return app


def test_missing_tenant_header_returns_400_for_stateful_route():
    client = TestClient(build_test_app())
    response = client.get("/api/settings")
    assert response.status_code == 400
    assert response.json()["detail"] == "X-Tenant-Id header is required"


def test_exempt_route_still_works_without_tenant_header():
    client = TestClient(build_test_app())
    response = client.get("/api/version")
    assert response.status_code == 200
```

- [ ] **Step 2: Run the failing middleware tests**

Run:
```bash
pytest tests/unit/app/test_tenant_identity.py -k "missing_tenant_header or exempt_route" -v
```

Expected:
- FAIL because current middleware still defaults to `default`

- [ ] **Step 3: Implement strict non-exempt behavior**

Update the middleware default and missing-header branch so non-exempt routes reject when `require_tenant=True`.

```python
class TenantIdentityMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        require_tenant: bool = True,
        default_tenant_id: str | None = None,
    ):
        super().__init__(app)
        self._require_tenant = require_tenant
        self._default_tenant_id = default_tenant_id
```

```python
if not is_exempt:
    if not tenant_id:
        if self._require_tenant:
            raise HTTPException(
                status_code=400,
                detail="X-Tenant-Id header is required",
            )
        tenant_id = self._default_tenant_id
```

- [ ] **Step 4: Add one invalid-header format regression test**

```python
def test_invalid_tenant_id_returns_400():
    client = TestClient(build_test_app())
    response = client.get(
        "/api/settings",
        headers={"X-Tenant-Id": "../bad"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid X-Tenant-Id format"
```

- [ ] **Step 5: Run the tenant identity tests**

Run:
```bash
pytest tests/unit/app/test_tenant_identity.py -v
```

Expected:
- PASS for strict tenant-header coverage

- [ ] **Step 6: Commit**

```bash
git add tests/unit/app/test_tenant_identity.py src/copaw/app/middleware/tenant_identity.py src/copaw/app/_app.py
git commit -m "fix(tenant): require tenant headers on stateful routes"
```

---

### Task 3: Make agent config and runtime resolution genuinely tenant-local

**Files:**
- Modify: `src/copaw/app/agent_context.py:28-164`
- Modify: `src/copaw/app/routers/agents.py`
- Modify: `src/copaw/config/utils.py:640-778`
- Test: `tests/unit/routers/test_agents_tenant_scope.py`

- [ ] **Step 1: Write the failing tenant-local agent resolution tests**

```python
def test_get_agent_for_request_uses_tenant_local_config(request_factory, monkeypatch):
    request = request_factory(headers={"X-Tenant-Id": "tenant-a"})

    tenant_config = type("Cfg", (), {
        "agents": type("Agents", (), {
            "active_agent": "alpha",
            "profiles": {"alpha": type("Ref", (), {"enabled": True})()},
        })()
    })()

    monkeypatch.setattr(
        "copaw.app.agent_context._get_tenant_aware_config",
        lambda tenant_id=None: tenant_config,
    )

    resolved = __import__("copaw.app.agent_context", fromlist=["get_active_agent_id"]).get_active_agent_id("tenant-a")
    assert resolved == "alpha"
```

```python
def test_agent_creation_defaults_to_tenant_workspace(client):
    response = client.post(
        "/api/agents",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"name": "Tenant Agent"},
    )

    assert response.status_code == 200
    assert "/tenant-a/workspaces/" in response.json()["workspace_dir"]
```

- [ ] **Step 2: Run the failing agent tests**

Run:
```bash
pytest tests/unit/routers/test_agents_tenant_scope.py -v
```

Expected:
- FAIL because tenant config/runtime lookup is still global in key paths

- [ ] **Step 3: Implement tenant-local config path resolution**

Introduce explicit tenant-scoped config loading in `src/copaw/app/agent_context.py` instead of the current placeholder fallback.

```python
def _get_tenant_aware_config(tenant_id: Optional[str] = None):
    if tenant_id is None:
        tenant_id = get_current_tenant_id()
    if tenant_id is None:
        return load_config()
    return load_config(get_tenant_config_path(tenant_id))
```

- [ ] **Step 4: Make runtime lookup tenant-first**

Replace direct app-global agent retrieval with tenant workspace retrieval where the request already has `request.state.workspace`, and only resolve agent IDs inside the tenant-local config namespace.

```python
workspace = getattr(request.state, "workspace", None)
if workspace is not None:
    return workspace
```

```python
config = _get_tenant_aware_config(tenant_id)
target_agent_id = target_agent_id or config.agents.active_agent or "default"
```

- [ ] **Step 5: Add a cross-tenant regression test**

```python
def test_tenant_b_cannot_resolve_tenant_a_active_agent(client):
    response = client.get(
        "/api/agent/current",
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert response.status_code in (200, 404)
    assert response.json() != {"agent_id": "tenant-a-only-agent"}
```

- [ ] **Step 6: Run the agent tests again**

Run:
```bash
pytest tests/unit/routers/test_agents_tenant_scope.py -v
```

Expected:
- PASS for tenant-local agent config/runtime coverage

- [ ] **Step 7: Commit**

```bash
git add tests/unit/routers/test_agents_tenant_scope.py src/copaw/app/agent_context.py src/copaw/app/routers/agents.py src/copaw/config/utils.py
git commit -m "fix(tenant): scope agent resolution to tenant config and runtime"
```

---

### Task 4: Remove tenant-business path fallback to global `WORKING_DIR`

**Files:**
- Modify: `src/copaw/config/utils.py:640-778`
- Test: `tests/unit/config/test_tenant_paths.py`

- [ ] **Step 1: Write the failing strict-path tests**

```python
import pytest

from copaw.config.context import TenantContextError
from copaw.config.utils import get_tenant_working_dir_strict, get_tenant_config_path_strict


def test_get_tenant_working_dir_strict_raises_without_tenant_context():
    with pytest.raises(TenantContextError):
        get_tenant_working_dir_strict()


def test_get_tenant_config_path_strict_uses_explicit_tenant():
    path = get_tenant_config_path_strict("tenant-a")
    assert str(path).endswith("tenant-a/config.json")
```

- [ ] **Step 2: Run the failing path tests**

Run:
```bash
pytest tests/unit/config/test_tenant_paths.py -v
```

Expected:
- FAIL if strict and non-strict helpers are still being used interchangeably in tenant-sensitive code

- [ ] **Step 3: Implement the minimal helper split**

Keep non-strict helpers only for explicitly system-level call sites, and move tenant-sensitive router/runtime code onto strict helpers.

```python
def get_tenant_working_dir(tenant_id: str | None = None) -> Path:
    if tenant_id is None:
        tenant_id = get_current_tenant_id()
    if tenant_id:
        return WORKING_DIR / tenant_id
    return WORKING_DIR
```

```python
def get_tenant_working_dir_strict(tenant_id: str | None = None) -> Path:
    if tenant_id is None:
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise TenantContextError(
                "Tenant context required. Ensure this code runs within a tenant-scoped request or context."
            )
    return WORKING_DIR / tenant_id
```

Then update tenant-sensitive callers to use the strict helpers.

- [ ] **Step 4: Add one router regression that proves missing tenant context does not silently hit global business paths**

```python
def test_tenant_sensitive_helper_call_does_not_fallback_to_global_path():
    with pytest.raises(TenantContextError):
        get_tenant_working_dir_strict(None)
```

- [ ] **Step 5: Run the path tests again**

Run:
```bash
pytest tests/unit/config/test_tenant_paths.py -v
```

Expected:
- PASS for strict helper behavior

- [ ] **Step 6: Commit**

```bash
git add tests/unit/config/test_tenant_paths.py src/copaw/config/utils.py
git commit -m "fix(tenant): require strict helpers for tenant business paths"
```

---

### Task 5: Restrict console push reads to tenant + session scope

**Files:**
- Modify: `src/copaw/app/console_push_store.py:157-176`
- Modify: `src/copaw/app/routers/console.py:204-222`
- Test: `tests/unit/app/test_console_push_store.py`
- Test: `tests/unit/routers/test_console_tenant_isolation.py`

- [ ] **Step 1: Write the failing session-scope tests**

```python
import pytest

from copaw.app.console_push_store import append, take


@pytest.mark.asyncio
async def test_messages_do_not_leak_across_sessions_within_same_tenant():
    await append("session-a", "msg-a", tenant_id="tenant-a")
    await append("session-b", "msg-b", tenant_id="tenant-a")

    taken = await take("session-a", tenant_id="tenant-a")

    assert [m["text"] for m in taken] == ["msg-a"]
```

```python
def test_push_messages_api_requires_session_id(client):
    response = client.get(
        "/api/console/push-messages",
        headers={"X-Tenant-Id": "tenant-a"},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run the failing push-store tests**

Run:
```bash
pytest tests/unit/app/test_console_push_store.py tests/unit/routers/test_console_tenant_isolation.py -v
```

Expected:
- FAIL because `/push-messages` still exposes tenant-wide recent messages without session scoping

- [ ] **Step 3: Implement the minimal API restriction**

Update `src/copaw/app/routers/console.py` to require `session_id` for the normal API path.

```python
@router.get("/push-messages")
async def get_push_messages(
    request: Request,
    session_id: str | None = Query(None, description="Session id"),
):
    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="session_id is required",
        )
    tenant_id = getattr(request.state, "tenant_id", None)
    messages = await take(session_id, tenant_id=tenant_id)
    return {"messages": messages}
```

- [ ] **Step 4: Keep `get_recent()` for internal diagnostics only**

Do not remove the helper immediately; stop exposing it through the normal user-facing API path.

- [ ] **Step 5: Run the push-store tests again**

Run:
```bash
pytest tests/unit/app/test_console_push_store.py tests/unit/routers/test_console_tenant_isolation.py -v
```

Expected:
- PASS for tenant + session scoped reads

- [ ] **Step 6: Commit**

```bash
git add tests/unit/app/test_console_push_store.py tests/unit/routers/test_console_tenant_isolation.py src/copaw/app/console_push_store.py src/copaw/app/routers/console.py
git commit -m "fix(tenant): scope console push reads to tenant sessions"
```

---

### Task 6: Bind workspace context into cron execution

**Files:**
- Modify: `src/copaw/app/crons/executor.py:19-115`
- Modify: `src/copaw/app/tenant_context.py`
- Test: `tests/unit/app/crons/test_tenant_cron_execution.py`

- [ ] **Step 1: Write the failing cron workspace-context tests**

```python
import pytest

from copaw.config.context import get_current_workspace_dir


@pytest.mark.asyncio
async def test_cron_execute_binds_workspace_context(executor, cron_job, tmp_path):
    cron_job.tenant_id = "tenant-a"
    cron_job.dispatch.target.user_id = "user-a"
    cron_job.dispatch.target.session_id = "session-a"
    cron_job.meta["workspace_dir"] = str(tmp_path / "tenant-a")

    await executor.execute(cron_job)

    assert get_current_workspace_dir() is None
```

The assertion checks cleanup; the body of the executor test should also capture the workspace during execution via a fake runner callback.

- [ ] **Step 2: Run the failing cron execution tests**

Run:
```bash
pytest tests/unit/app/crons/test_tenant_cron_execution.py -v
```

Expected:
- FAIL because cron currently binds tenant/user only

- [ ] **Step 3: Extend the shared context helper to support workspace_dir**

```python
with bind_tenant_context(
    tenant_id=tenant_id,
    user_id=target_user_id,
    workspace_dir=workspace_dir,
):
    await self._execute_job(...)
```

- [ ] **Step 4: Derive workspace_dir from the job or workspace-local manager context**

Use the tenant workspace path already known at the cron manager / workspace layer instead of guessing from global state.

```python
workspace_dir = dispatch_meta.get("workspace_dir")
```

- [ ] **Step 5: Add a cleanup regression test**

```python
@pytest.mark.asyncio
async def test_cron_workspace_context_resets_after_timeout(executor, cron_job, tmp_path):
    cron_job.meta["workspace_dir"] = str(tmp_path / "tenant-a")
    with pytest.raises(Exception):
        await executor.execute(cron_job)
    assert get_current_workspace_dir() is None
```

- [ ] **Step 6: Run the cron execution tests again**

Run:
```bash
pytest tests/unit/app/crons/test_tenant_cron_execution.py -v
```

Expected:
- PASS for workspace context binding and cleanup

- [ ] **Step 7: Commit**

```bash
git add tests/unit/app/crons/test_tenant_cron_execution.py src/copaw/app/crons/executor.py src/copaw/app/tenant_context.py
git commit -m "fix(tenant): bind workspace context during cron execution"
```

---

### Task 7: Make heartbeat execution explicitly tenant-bound

**Files:**
- Modify: `src/copaw/app/crons/heartbeat.py:126-212`
- Modify: `src/copaw/app/workspace/workspace.py:241-261`
- Test: `tests/unit/app/crons/test_tenant_heartbeat.py`

- [ ] **Step 1: Write the failing heartbeat path tests**

```python
from pathlib import Path


def test_run_heartbeat_uses_workspace_dir_when_provided(tmp_path, heartbeat_runner):
    workspace_dir = tmp_path / "tenant-a"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "HEARTBEAT.md").write_text("ping", encoding="utf-8")

    path = heartbeat_runner.resolve_heartbeat_path(workspace_dir=workspace_dir)

    assert path == workspace_dir / "HEARTBEAT.md"
```

```python
def test_tenant_b_heartbeat_does_not_read_tenant_a_file(tmp_path, heartbeat_runner):
    tenant_a = tmp_path / "tenant-a"
    tenant_b = tmp_path / "tenant-b"
    tenant_a.mkdir(parents=True)
    tenant_b.mkdir(parents=True)
    (tenant_a / "HEARTBEAT.md").write_text("tenant-a", encoding="utf-8")
    (tenant_b / "HEARTBEAT.md").write_text("tenant-b", encoding="utf-8")

    assert heartbeat_runner.resolve_heartbeat_path(workspace_dir=tenant_b) == tenant_b / "HEARTBEAT.md"
```

- [ ] **Step 2: Run the failing heartbeat tests**

Run:
```bash
pytest tests/unit/app/crons/test_tenant_heartbeat.py -v
```

Expected:
- FAIL if heartbeat path resolution is still implicit or untestable

- [ ] **Step 3: Extract a tiny explicit path helper inside heartbeat execution**

```python
def resolve_heartbeat_path(workspace_dir: Optional[Path] = None) -> Path:
    if workspace_dir is not None:
        return Path(workspace_dir) / HEARTBEAT_FILE
    return get_heartbeat_query_path()
```

Then use it in `run_heartbeat(...)`.

- [ ] **Step 4: Ensure workspace-local cron manager passes workspace context into heartbeat execution**

```python
await run_heartbeat(
    runner=self.runner,
    channel_manager=self.channel_manager,
    agent_id=self.agent_id,
    workspace_dir=self.workspace_dir,
)
```

- [ ] **Step 5: Run the heartbeat tests again**

Run:
```bash
pytest tests/unit/app/crons/test_tenant_heartbeat.py -v
```

Expected:
- PASS for explicit tenant-bound heartbeat path resolution

- [ ] **Step 6: Commit**

```bash
git add tests/unit/app/crons/test_tenant_heartbeat.py src/copaw/app/crons/heartbeat.py src/copaw/app/workspace/workspace.py
git commit -m "fix(tenant): bind heartbeat execution to tenant workspaces"
```

---

### Task 8: Replace placeholder tenant tests with evidence-grade verification

**Files:**
- Modify: `tests/unit/app/test_tenant_identity.py`
- Modify: `tests/unit/app/test_tenant_workspace.py`
- Modify: `tests/unit/app/test_tenant_middleware.py`
- Create: `tests/unit/routers/test_envs_tenant_scope.py`
- Create: `tests/unit/routers/test_agents_tenant_scope.py`
- Create: `tests/unit/routers/test_console_tenant_isolation.py`
- Create: `tests/unit/app/crons/test_tenant_cron_execution.py`
- Create: `tests/unit/app/crons/test_tenant_heartbeat.py`

- [ ] **Step 1: Remove `pass` placeholders from middleware-order tests**

Replace placeholder tests with assertions on actual middleware registration or explicit request behavior.

```python
def test_stateful_route_requires_tenant_header(client):
    response = client.get("/api/settings")
    assert response.status_code == 400
```

- [ ] **Step 2: Remove `@pytest.mark.skip` from tests that can run with lightweight fixtures**

Prefer focused app/router fixtures over full production dependency graphs.

```python
@pytest.fixture
def app():
    app = FastAPI()
    ...
    return app
```

- [ ] **Step 3: Add one end-to-end style regression per corrected blocker**

Required minimum set:
- env custom-path write does not mutate `os.environ`
- missing `X-Tenant-Id` returns 400 on stateful routes
- tenant B cannot resolve tenant A agent namespace
- `/console/push-messages` requires `session_id`
- cron binds workspace context
- heartbeat reads from the provided tenant workspace path

- [ ] **Step 4: Run the focused tenant test suite**

Run:
```bash
pytest \
  tests/unit/app/test_tenant_identity.py \
  tests/unit/app/test_tenant_workspace.py \
  tests/unit/app/test_tenant_middleware.py \
  tests/unit/app/test_console_push_store.py \
  tests/unit/config/test_tenant_paths.py \
  tests/unit/routers/test_envs_tenant_scope.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/routers/test_console_tenant_isolation.py \
  tests/unit/app/crons/test_tenant_cron_execution.py \
  tests/unit/app/crons/test_tenant_heartbeat.py -v
```

Expected:
- PASS with no placeholder-only coverage left for the remediated areas

- [ ] **Step 5: Commit**

```bash
git add tests/unit/app/test_tenant_identity.py tests/unit/app/test_tenant_workspace.py tests/unit/app/test_tenant_middleware.py tests/unit/app/test_console_push_store.py tests/unit/config/test_tenant_paths.py tests/unit/routers/test_envs_tenant_scope.py tests/unit/routers/test_agents_tenant_scope.py tests/unit/routers/test_console_tenant_isolation.py tests/unit/app/crons/test_tenant_cron_execution.py tests/unit/app/crons/test_tenant_heartbeat.py
git commit -m "test(tenant): replace placeholder isolation tests with real verification"
```

---

### Task 9: Sync audited documentation after code fixes and verification

**Files:**
- Modify: `docs/superpowers/implementation/2026-04-02-multi-tenant-implementation-audited.md`
- Modify: `docs/superpowers/review/2026-04-02-multi-tenant-isolation-review-audited.md`
- Optionally modify: `docs/superpowers/implementation/2026-04-02-multi-tenant-implementation.md`

- [ ] **Step 1: Re-read the audited docs after the code/test changes**

Confirm each previously partial area is now either:
- fixed and verified
- still partial
- intentionally deferred

- [ ] **Step 2: Update the audited implementation summary to reflect real post-fix status**

Use language like this, not blanket completion claims:

```markdown
- Confirmed complete after remediation: tenant env file writes no longer mutate process-global `os.environ`
- Confirmed complete after remediation: non-exempt routes reject missing `X-Tenant-Id`
- Confirmed complete after remediation: cron execution restores tenant, user, and workspace context
```

- [ ] **Step 3: Update the audited review to mark resolved findings explicitly**

```markdown
### 1. Tenant secrets still mutate process-global `os.environ`
**Post-remediation status:** Resolved
```

- [ ] **Step 4: Run a final sanity pass on wording**

Checklist:
- no “complete” claim without code + test evidence
- no stale references to pre-fix behavior
- no contradiction between implementation and review docs

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/implementation/2026-04-02-multi-tenant-implementation-audited.md docs/superpowers/review/2026-04-02-multi-tenant-isolation-review-audited.md
git commit -m "docs(tenant): sync audited isolation docs after remediation"
```

---

## Self-review

### Spec coverage
Covered remediation areas:
- tenant env global mutation
- strict missing-header enforcement
- tenant-local agent resolution
- strict tenant business path usage
- same-tenant session leakage in console push reads
- cron workspace context restoration
- heartbeat tenant workspace binding
- replacement of weak verification with real evidence
- post-fix documentation sync

Not included intentionally:
- large-scale runtime architecture rewrite beyond what is needed to close the audited gaps
- unrelated refactors in settings/workspace archive code that were already assessed as strong

### Placeholder scan
The plan avoids TBD/TODO placeholders and gives concrete files, tests, commands, and expected outcomes for each task.

### Type consistency
The plan consistently uses:
- `X-Tenant-Id`
- `request.state.workspace`
- tenant-scoped config lookup
- `workspace_dir`
- audited implementation/review docs as the source of current remediation status
