# Effective Tenant Scope Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate ambiguous tenant/scope handling in memory-adjacent runtime code so same logical `tenant_id` with different `source_id` always stays isolated across workspace, config, memory, hooks, and cron flows.

**Architecture:** Preserve the current runtime-scope model, but make it explicit in code. Runtime-facing modules should accept and propagate `effective_tenant_id` or `runtime_tenant_id`, while request-facing modules continue resolving logical `tenant_id + source_id + scope_id` into a canonical scope before calling runtime services. Tighten weak fallback points and add regression tests that prove source-scoped tenants do not share runtime state.

**Tech Stack:** Python 3.12, FastAPI, pytest, GitNexus-indexed SWE runtime

---

### Task 1: Lock Down Scope Terminology In Runtime Entrypoints

**Files:**
- Modify: `src/swe/app/multi_agent_manager.py`
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/agents/memory/base_memory_manager.py`
- Modify: `src/swe/agents/memory/reme_light_memory_manager.py`
- Test: `tests/unit/routers/test_agents_tenant_scope.py`
- Test: `tests/unit/agents/test_memory_manager_tenant_scope.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_multi_agent_manager_uses_runtime_scope_key(monkeypatch):
    calls = []

    monkeypatch.setattr(
        multi_agent_manager,
        "load_config",
        lambda path=None: calls.append(path) or SimpleNamespace(
            agents=SimpleNamespace(
                profiles={
                    "default": SimpleNamespace(
                        workspace_dir="/tmp/runtime-scope/workspaces/default",
                    ),
                },
            ),
        ),
    )

    manager = multi_agent_manager.MultiAgentManager()
    asyncio.run(
        manager.get_agent(
            "default",
            effective_tenant_id="dGVuYW50LWE.c291cmNlLWE",
        ),
    )

    assert str(calls[0]).endswith(
        "dGVuYW50LWE.c291cmNlLWE/config.json",
    )


def test_base_memory_manager_stores_effective_tenant_id():
    manager = _ConcreteMemoryManager(
        working_dir="/tmp/ws",
        agent_id="default",
        tenant_id="dGVuYW50LWE.c291cmNlLWE",
    )

    assert manager.tenant_id == "dGVuYW50LWE.c291cmNlLWE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/unit/routers/test_agents_tenant_scope.py tests/unit/agents/test_memory_manager_tenant_scope.py -v`
Expected: FAIL because runtime-facing APIs still expose ambiguous `tenant_id` naming and tests/assertions do not match current interfaces.

- [ ] **Step 3: Write the minimal implementation**

```python
class MultiAgentManager:
    async def get_agent(
        self,
        agent_id: str,
        effective_tenant_id: Optional[str] = None,
    ) -> Workspace:
        cache_key = self._cache_key(agent_id, effective_tenant_id)
        config = self._load_agent_config_for_tenant(effective_tenant_id)
        instance = Workspace(
            agent_id=agent_id,
            workspace_dir=agent_ref.workspace_dir,
            tenant_id=effective_tenant_id,
            source_system_config_service=self._source_system_config_service,
        )


class AgentRunner:
    def __init__(self, agent_id: str, workspace_dir: str, tenant_id: str | None = None, **kwargs):
        self.tenant_id = (
            resolve_runtime_tenant_id(tenant_id, None)
            if tenant_id is not None
            else None
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/unit/routers/test_agents_tenant_scope.py tests/unit/agents/test_memory_manager_tenant_scope.py -v`
Expected: PASS with runtime-facing code consistently treating the incoming tenant value as an already-resolved runtime scope.

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/multi_agent_manager.py src/swe/app/runner/runner.py src/swe/agents/memory/base_memory_manager.py src/swe/agents/memory/reme_light_memory_manager.py tests/unit/routers/test_agents_tenant_scope.py tests/unit/agents/test_memory_manager_tenant_scope.py
git commit -m "refactor(scope): clarify runtime tenant contract"
```

### Task 2: Separate Logical Tenant From Effective Scope In Request Context

**Files:**
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/agents/tool_guard_mixin.py`
- Modify: `src/swe/agents/hooks/memory_compaction.py`
- Modify: `src/swe/agents/command_handler.py`
- Test: `tests/unit/agents/test_command_handler_tenant_scope.py`
- Test: `tests/unit/agents/test_source_tool_result_compact_config.py`
- Create: `tests/unit/agents/test_tool_guard_scope_context.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_tool_guard_loads_config_from_effective_tenant_scope(monkeypatch):
    observed = {}

    monkeypatch.setattr(
        "swe.agents.tool_guard_mixin.load_config",
        lambda path=None: observed.setdefault("path", path) or SimpleNamespace(hooks=HookConfig()),
    )

    mixin = _ToolGuardHarness(
        request_context={
            "tenant_id": "tenant-a",
            "effective_tenant_id": "dGVuYW50LWE.c291cmNlLWE",
        },
    )

    mixin._load_tenant_hook_config()

    assert str(observed["path"]).endswith(
        "dGVuYW50LWE.c291cmNlLWE/config.json",
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/unit/agents/test_command_handler_tenant_scope.py tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_tool_guard_scope_context.py -v`
Expected: FAIL because request context still conflates logical tenant and effective scope under the same `tenant_id` field.

- [ ] **Step 3: Write the minimal implementation**

```python
request_context = {
    "tenant_id": logical_tenant_id,
    "effective_tenant_id": self.tenant_id or "",
    "source_id": source_id or "",
}

def _load_tenant_hook_config(self) -> HookConfig:
    effective_tenant_id = (
        self._request_context.get("effective_tenant_id")
        or self._request_context.get("tenant_id")
    )
    config_path = (
        get_tenant_config_path(effective_tenant_id)
        if effective_tenant_id
        else None
    )
    return load_config(config_path).hooks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/unit/agents/test_command_handler_tenant_scope.py tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_tool_guard_scope_context.py -v`
Expected: PASS with request context preserving both logical tenant identity and effective runtime scope.

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/runner/runner.py src/swe/agents/tool_guard_mixin.py src/swe/agents/hooks/memory_compaction.py src/swe/agents/command_handler.py tests/unit/agents/test_command_handler_tenant_scope.py tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_tool_guard_scope_context.py
git commit -m "fix(scope): split logical tenant from runtime scope context"
```

### Task 3: Tighten Weak Request Helpers To Prefer Effective Scope

**Files:**
- Modify: `src/swe/app/middleware/tenant_workspace.py`
- Modify: `src/swe/app/routers/settings.py`
- Modify: `src/swe/app/routers/envs.py`
- Modify: `src/swe/app/routers/workspace.py`
- Test: `tests/unit/app/test_tenant_workspace_scope_resolution.py`
- Test: `tests/unit/routers/test_workspace_scope_resolution.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_settings_path_prefers_effective_tenant_id():
    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="tenant-a",
            effective_tenant_id="dGVuYW50LWE.c291cmNlLWE",
            scope_id=None,
        ),
    )

    path = settings._get_settings_file(request)

    assert "dGVuYW50LWE.c291cmNlLWE" in str(path)


def test_workspace_download_filename_uses_effective_scope_when_available():
    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="tenant-a",
            effective_tenant_id="dGVuYW50LWE.c291cmNlLWE",
        ),
    )

    assert workspace_router._download_tenant_label(request) == "dGVuYW50LWE.c291cmNlLWE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_workspace_scope_resolution.py tests/unit/routers/test_workspace_scope_resolution.py -v`
Expected: FAIL because helper functions still fall back to logical tenant too early or do not expose the chosen runtime scope consistently.

- [ ] **Step 3: Write the minimal implementation**

```python
def _get_effective_request_tenant_id(request: Request) -> str | None:
    scope_id = getattr(request.state, "scope_id", None)
    if isinstance(scope_id, str) and scope_id:
        return canonicalize_scope_id(scope_id)

    effective_tenant_id = getattr(request.state, "effective_tenant_id", None)
    if isinstance(effective_tenant_id, str) and effective_tenant_id:
        return effective_tenant_id

    tenant_id = getattr(request.state, "tenant_id", None)
    if isinstance(tenant_id, str) and tenant_id:
        return tenant_id
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_workspace_scope_resolution.py tests/unit/routers/test_workspace_scope_resolution.py -v`
Expected: PASS with request helpers consistently preferring canonical runtime scope over logical tenant identity.

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/middleware/tenant_workspace.py src/swe/app/routers/settings.py src/swe/app/routers/envs.py src/swe/app/routers/workspace.py tests/unit/app/test_tenant_workspace_scope_resolution.py tests/unit/routers/test_workspace_scope_resolution.py
git commit -m "fix(scope): prefer effective tenant in request helpers"
```

### Task 4: Prove Cross-Module Source Isolation End-To-End

**Files:**
- Create: `tests/integration/test_source_scoped_runtime_isolation.py`
- Modify: `tests/unit/app/test_external_cron_scope_refresh.py`
- Modify: `tests/unit/app/test_scheduled_run_source_system_config_binding.py`
- Modify: `tests/unit/app/test_heartbeat_tenant_scope.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_same_logical_tenant_different_sources_use_distinct_runtime_state():
    source_a = encode_scope_id("tenant-a", "source-a")
    source_b = encode_scope_id("tenant-a", "source-b")

    manager = MultiAgentManager()
    workspace_a = await manager.get_agent("default", effective_tenant_id=source_a)
    workspace_b = await manager.get_agent("default", effective_tenant_id=source_b)

    assert workspace_a is not workspace_b
    assert workspace_a.tenant_id == source_a
    assert workspace_b.tenant_id == source_b
    assert workspace_a.memory_manager.tenant_id == source_a
    assert workspace_b.memory_manager.tenant_id == source_b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/integration/test_source_scoped_runtime_isolation.py tests/unit/app/test_external_cron_scope_refresh.py tests/unit/app/test_scheduled_run_source_system_config_binding.py tests/unit/app/test_heartbeat_tenant_scope.py -v`
Expected: FAIL until every call site and test fixture uses the clarified runtime-scope contract consistently.

- [ ] **Step 3: Write the minimal implementation**

```python
runtime_tenant_id = resolve_runtime_tenant_id(tenant_id, source_id)
mgr = await _get_cron_manager(manager, runtime_tenant_id, agent_id)

workspace = await manager.get_agent(
    target_agent_id,
    effective_tenant_id=effective_tenant_id,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/integration/test_source_scoped_runtime_isolation.py tests/unit/app/test_external_cron_scope_refresh.py tests/unit/app/test_scheduled_run_source_system_config_binding.py tests/unit/app/test_heartbeat_tenant_scope.py -v`
Expected: PASS with distinct runtime state for same logical tenant under different source scopes.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_source_scoped_runtime_isolation.py tests/unit/app/test_external_cron_scope_refresh.py tests/unit/app/test_scheduled_run_source_system_config_binding.py tests/unit/app/test_heartbeat_tenant_scope.py
git commit -m "test(scope): cover source-scoped runtime isolation"
```

### Task 5: Final Verification And Change Audit

**Files:**
- Modify: `docs/superpowers/plans/2026-06-01-effective-tenant-scope-hardening.md`

- [ ] **Step 1: Run focused regression suites**

Run: `venv/bin/python -m pytest tests/unit/agents/test_memory_manager_tenant_scope.py tests/unit/agents/test_command_handler_tenant_scope.py tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/routers/test_agents_tenant_scope.py tests/unit/app/test_external_cron_scope_refresh.py tests/unit/app/test_scheduled_run_source_system_config_binding.py tests/unit/app/test_heartbeat_tenant_scope.py -v`
Expected: PASS for all memory-adjacent scope regression suites.

- [ ] **Step 2: Run broader scope-sensitive suites**

Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_workspace_scope_resolution.py tests/unit/routers/test_workspace_scope_resolution.py tests/unit/agents/test_tool_guard_scope_context.py tests/integration/test_source_scoped_runtime_isolation.py -v`
Expected: PASS for helper, hook, and integration isolation coverage.

- [ ] **Step 3: Inspect the changed blast radius**

Run: `npx gitnexus analyze detect-changes --repo CoPaw`
Expected: Output should be limited to workspace/runtime scope propagation, request helper cleanup, and associated tests; no unrelated routes or market/source business logic should appear.

- [ ] **Step 4: Update the plan with any deviations discovered during execution**

```markdown
## Execution Notes

- Record any interface rename that required fixture updates.
- Record any additional scope-sensitive module discovered during implementation.
- Record any tests that needed rewritten stubs because runtime constructors changed.
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-06-01-effective-tenant-scope-hardening.md
git commit -m "docs: finalize runtime scope hardening plan notes"
```
