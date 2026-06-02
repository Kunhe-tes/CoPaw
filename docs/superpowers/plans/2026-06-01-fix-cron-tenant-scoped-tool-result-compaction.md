# Cron Tenant-Scoped Tool Result Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cron and other tenant-scoped runtime paths always resolve `agent.json` from the correct tenant/scope when reading `running.tool_result_compact` and other memory-related runtime config.

**Architecture:** Push `tenant_id` down into the memory-manager layer so tenant scope becomes part of the runtime object graph instead of being re-derived ad hoc. Then replace every unscoped `load_agent_config(...)` call inside the memory/config hot-reload path with a single tenant-aware helper, and lock the behavior with regression tests that distinguish global `config.json` from tenant-local `agent.json`.

**Tech Stack:** Python, pytest, Pydantic config models, workspace service wiring, cron/runtime tenant context

---

## File Map

- Modify: `src/swe/agents/memory/base_memory_manager.py`
  Add `tenant_id` to the shared memory-manager base class and persist it on the instance.
- Modify: `src/swe/agents/memory/reme_light_memory_manager.py`
  Accept `tenant_id`, centralize tenant-aware agent-config loading, and update every memory/runtime config consumer to use it.
- Modify: `src/swe/app/workspace/workspace.py`
  Pass workspace `tenant_id` into the memory-manager constructor when services are built.
- Modify: `src/swe/agents/hooks/memory_compaction.py`
  Stop reloading agent config without tenant scope during pre-reasoning compaction.
- Modify: `src/swe/agents/command_handler.py`
  Stop reloading agent config without tenant scope for `/history` and related commands.
- Modify: `tests/unit/agents/test_source_tool_result_compact_config.py`
  Add the exact regression for the reported cron/tool-result-compaction bug.
- Create: `tests/unit/agents/test_memory_manager_tenant_scope.py`
  Add focused unit tests for tenant-aware config resolution inside the memory-manager layer.
- Create: `tests/unit/agents/test_command_handler_tenant_scope.py`
  Add a small regression test for command-handler hot-reload config reads.

## Implementation Assumptions

- The current bug is caused by unscoped `load_agent_config(...)` calls, not by `source_system_config` defaults. Source config should remain request-level override only.
- `create_model_and_formatter(...)` is already tenant-aware through runtime context and does not need changes for this bug.
- The minimal safe architecture change is to make `tenant_id` a first-class property on `BaseMemoryManager`; trying to patch only one call site would leave the same bug class in adjacent methods.
- `CommandHandler` should continue to support `memory_manager is None`, but when a memory manager exists it must reuse the same tenant scope as the active workspace.

### Task 1: Write Repro Tests For Tenant-Scoped Tool Result Compaction

**Files:**
- Modify: `tests/unit/agents/test_source_tool_result_compact_config.py`
- Create: `tests/unit/agents/test_memory_manager_tenant_scope.py`
- Test: `tests/unit/agents/test_source_tool_result_compact_config.py`
- Test: `tests/unit/agents/test_memory_manager_tenant_scope.py`

- [ ] **Step 1: Add the failing hook regression test**

Append this test to `tests/unit/agents/test_source_tool_result_compact_config.py`:

```python
@pytest.mark.asyncio
async def test_memory_compaction_hook_uses_tenant_scoped_agent_config(
    tmp_path,
    monkeypatch,
):
    """Hook compaction should use tenant agent.json instead of global defaults."""
    from swe.config.config import (
        Config,
        AgentsConfig,
        AgentProfileConfig,
        AgentProfileRef,
        AgentsRunningConfig,
        save_agent_config,
    )
    from swe.config.utils import save_config
    import swe.config.utils as config_utils
    import swe.config.config as config_module
    import swe.agents.hooks.memory_compaction as memory_compaction

    monkeypatch.setattr(config_utils, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(config_module, "WORKING_DIR", tmp_path)

    global_workspace = tmp_path / "workspaces" / "default"
    tenant_workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    global_workspace.mkdir(parents=True)
    tenant_workspace.mkdir(parents=True)

    save_config(
        Config(
            agents=AgentsConfig(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(global_workspace),
                    ),
                },
            ),
        ),
        tmp_path / "config.json",
    )
    save_config(
        Config(
            agents=AgentsConfig(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(tenant_workspace),
                    ),
                },
            ),
        ),
        tmp_path / "tenant-a" / "config.json",
    )

    save_agent_config(
        "default",
        AgentProfileConfig(
            id="default",
            name="Global",
            workspace_dir=str(global_workspace),
            running=AgentsRunningConfig(
                tool_result_compact={
                    "enabled": True,
                    "recent_n": 2,
                    "old_max_bytes": 3000,
                    "recent_max_bytes": 50000,
                    "retention_days": 5,
                },
                memory_summary={"memory_summary_enabled": False},
            ),
        ),
        config_path=tmp_path / "config.json",
    )
    save_agent_config(
        "default",
        AgentProfileConfig(
            id="default",
            name="Tenant",
            workspace_dir=str(tenant_workspace),
            running=AgentsRunningConfig(
                tool_result_compact={
                    "enabled": True,
                    "recent_n": 10,
                    "old_max_bytes": 50000,
                    "recent_max_bytes": 50000,
                    "retention_days": 5,
                },
                memory_summary={"memory_summary_enabled": False},
            ),
        ),
        config_path=tmp_path / "tenant-a" / "config.json",
    )

    token_counter = SimpleNamespace(count=AsyncMock(return_value=0))
    memory_manager = SimpleNamespace(
        agent_id="default",
        tenant_id="tenant-a",
        compact_tool_result=AsyncMock(),
        check_context=AsyncMock(return_value=([], [], True)),
    )
    agent = SimpleNamespace(
        name="agent",
        sys_prompt="",
        memory=SimpleNamespace(
            get_compressed_summary=lambda: "",
            get_memory=AsyncMock(return_value=["dummy"]),
        ),
        print=AsyncMock(),
    )
    monkeypatch.setattr(
        memory_compaction,
        "get_swe_token_counter",
        lambda _config: token_counter,
    )

    await MemoryCompactionHook(memory_manager)(agent, {})

    assert (
        memory_manager.compact_tool_result.await_args.kwargs["old_max_bytes"]
        == 50000
    )
    assert (
        memory_manager.compact_tool_result.await_args.kwargs["recent_n"]
        == 10
    )
```

- [ ] **Step 2: Add the failing memory-manager tenant-scope tests**

Create `tests/unit/agents/test_memory_manager_tenant_scope.py` with:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.agents.memory.reme_light_memory_manager import ReMeLightMemoryManager


def test_memory_manager_load_agent_config_uses_instance_tenant_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_load_agent_config(agent_id: str, tenant_id: str | None = None):
        calls.append((agent_id, tenant_id))
        return SimpleNamespace(
            running=SimpleNamespace(
                embedding_config=SimpleNamespace(
                    backend="openai",
                    api_key="",
                    base_url="https://tenant.example",
                    model_name="embed-tenant",
                    dimensions=1024,
                    enable_cache=True,
                    use_dimensions=True,
                ),
            ),
        )

    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.load_agent_config",
        fake_load_agent_config,
    )

    manager = object.__new__(ReMeLightMemoryManager)
    manager.agent_id = "default"
    manager.tenant_id = "tenant-a"
    manager._warn_if_version_mismatch = lambda: None

    config = manager.get_embedding_config()

    assert config["base_url"] == "https://tenant.example"
    assert calls == [("default", "tenant-a")]


@pytest.mark.asyncio
async def test_summary_memory_uses_tenant_scoped_tool_result_compact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, int] = {}

    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.load_agent_config",
        lambda agent_id, tenant_id=None: SimpleNamespace(
            agent_id=agent_id,
            language="zh",
            running=SimpleNamespace(
                max_input_length=128000,
                context_compact=SimpleNamespace(
                    memory_compact_ratio=0.8,
                    compact_with_thinking_block=False,
                ),
                tool_result_compact=SimpleNamespace(
                    enabled=True,
                    recent_n=10,
                    old_max_bytes=50000,
                    recent_max_bytes=50000,
                    retention_days=5,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.get_swe_token_counter",
        lambda _config: object(),
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.set_current_recent_max_bytes",
        lambda value: observed.setdefault("recent_max_bytes", value),
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.set_current_workspace_dir",
        lambda _path: None,
    )

    manager = object.__new__(ReMeLightMemoryManager)
    manager.agent_id = "default"
    manager.tenant_id = "tenant-a"
    manager.working_dir = str(Path("/tmp/ws"))
    manager._warn_if_version_mismatch = lambda: None
    manager._prepare_model_formatter = lambda: None
    manager.chat_model = object()
    manager.formatter = object()
    manager.summary_toolkit = object()
    manager._reme = SimpleNamespace(
        summary_memory=AsyncMock(return_value="ok"),
    )

    await manager.summary_memory(messages=[])

    assert observed["recent_max_bytes"] == 50000
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_memory_manager_tenant_scope.py -q`

Expected: FAIL because the runtime still resolves `old_max_bytes=3000` and because `ReMeLightMemoryManager` does not yet carry `tenant_id`.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_memory_manager_tenant_scope.py
git commit -m "test: capture tenant-scoped memory config regressions"
```

### Task 2: Push Tenant Scope Into The Memory-Manager Layer

**Files:**
- Modify: `src/swe/agents/memory/base_memory_manager.py`
- Modify: `src/swe/agents/memory/reme_light_memory_manager.py`
- Modify: `src/swe/app/workspace/workspace.py`
- Test: `tests/unit/agents/test_memory_manager_tenant_scope.py`

- [ ] **Step 1: Update the base class constructor signature**

Change `src/swe/agents/memory/base_memory_manager.py` to:

```python
class BaseMemoryManager(ABC):
    def __init__(
        self,
        working_dir: str,
        agent_id: str,
        tenant_id: str | None = None,
    ):
        self.working_dir: str = working_dir
        self.agent_id: str = agent_id
        self.tenant_id: str | None = tenant_id
        self.chat_model: Optional[ChatModelBase] = None
        self.formatter: Optional[FormatterBase] = None
        self.summary_tasks: list[asyncio.Task] = []
```

- [ ] **Step 2: Update the ReMeLight constructor and add a tenant-aware loader helper**

Update `src/swe/agents/memory/reme_light_memory_manager.py`:

```python
class ReMeLightMemoryManager(BaseMemoryManager):
    def __init__(
        self,
        working_dir: str,
        agent_id: str,
        tenant_id: str | None = None,
    ):
        super().__init__(
            working_dir=working_dir,
            agent_id=agent_id,
            tenant_id=tenant_id,
        )
        ...

    def _load_agent_config(self, tenant_id: str | None = None):
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else self.tenant_id
        )
        return load_agent_config(
            self.agent_id,
            tenant_id=resolved_tenant_id,
        )
```

- [ ] **Step 3: Wire workspace tenant scope into memory-manager construction**

Update `src/swe/app/workspace/workspace.py`:

```python
init_args=lambda ws: {
    "working_dir": str(ws.workspace_dir),
    "agent_id": ws.agent_id,
    "tenant_id": ws.tenant_id,
},
```

- [ ] **Step 4: Run the focused tests**

Run: `venv/bin/python -m pytest tests/unit/agents/test_memory_manager_tenant_scope.py -q`

Expected: PASS for constructor/helper scope propagation tests.

- [ ] **Step 5: Commit the structural tenant-scope change**

```bash
git add src/swe/agents/memory/base_memory_manager.py src/swe/agents/memory/reme_light_memory_manager.py src/swe/app/workspace/workspace.py tests/unit/agents/test_memory_manager_tenant_scope.py
git commit -m "refactor(memory): propagate tenant scope into memory managers"
```

### Task 3: Replace Every Unscoped Agent Config Reload In Memory Runtime

**Files:**
- Modify: `src/swe/agents/memory/reme_light_memory_manager.py`
- Modify: `src/swe/agents/hooks/memory_compaction.py`
- Modify: `src/swe/agents/command_handler.py`
- Test: `tests/unit/agents/test_source_tool_result_compact_config.py`
- Test: `tests/unit/agents/test_memory_manager_tenant_scope.py`

- [ ] **Step 1: Replace all unscoped loads in `ReMeLightMemoryManager`**

In `src/swe/agents/memory/reme_light_memory_manager.py`, replace these call sites:

```python
agent_config = load_agent_config(self.agent_id)
cfg = load_agent_config(self.agent_id).running.embedding_config
```

with:

```python
agent_config = self._load_agent_config()
cfg = self._load_agent_config().running.embedding_config
```

Apply this to the methods currently reading config at:
- `__init__`
- `get_embedding_config`
- `compact_memory`
- `summary_memory`
- `get_in_memory_memory`

- [ ] **Step 2: Make `MemoryCompactionHook` use memory-manager tenant scope**

Update `src/swe/agents/hooks/memory_compaction.py`:

```python
agent_config = load_agent_config(
    self.memory_manager.agent_id,
    tenant_id=getattr(self.memory_manager, "tenant_id", None),
)
```

Keep the rest of the compaction logic unchanged so the regression only fixes scope resolution.

- [ ] **Step 3: Make `CommandHandler` use memory-manager tenant scope**

Update `src/swe/agents/command_handler.py`:

```python
def _get_agent_config(self):
    tenant_id = getattr(self.memory_manager, "tenant_id", None)
    return load_agent_config(
        self.memory_manager.agent_id,
        tenant_id=tenant_id,
    )
```

If you need to preserve the `memory_manager is None` case, use:

```python
if self.memory_manager is None:
    raise RuntimeError("CommandHandler requires memory_manager")
```

instead of silently falling back to global config.

- [ ] **Step 4: Run the full regression suite for the bug path**

Run: `venv/bin/python -m pytest tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_memory_manager_tenant_scope.py -q`

Expected: PASS, including the assertion that `old_max_bytes == 50000`.

- [ ] **Step 5: Commit the scope-fix pass**

```bash
git add src/swe/agents/memory/reme_light_memory_manager.py src/swe/agents/hooks/memory_compaction.py src/swe/agents/command_handler.py tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_memory_manager_tenant_scope.py
git commit -m "fix(runtime): use tenant-scoped agent config in memory paths"
```

### Task 4: Add Small Guard Tests For Adjacent Hot-Reload Consumers

**Files:**
- Create: `tests/unit/agents/test_command_handler_tenant_scope.py`
- Modify: `tests/unit/agents/test_memory_manager_tenant_scope.py`
- Test: `tests/unit/agents/test_command_handler_tenant_scope.py`

- [ ] **Step 1: Add the command-handler regression test**

Create `tests/unit/agents/test_command_handler_tenant_scope.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from swe.agents.command_handler import CommandHandler


def test_get_agent_config_uses_memory_manager_tenant_scope(
    monkeypatch,
) -> None:
    observed: list[tuple[str, str | None]] = []

    def fake_load_agent_config(agent_id: str, tenant_id: str | None = None):
        observed.append((agent_id, tenant_id))
        return SimpleNamespace(running=SimpleNamespace(history_max_length=1234))

    monkeypatch.setattr(
        "swe.agents.command_handler.load_agent_config",
        fake_load_agent_config,
    )

    handler = CommandHandler(
        agent_name="Friday",
        memory=SimpleNamespace(),
        memory_manager=SimpleNamespace(
            agent_id="default",
            tenant_id="tenant-a",
        ),
        enable_memory_manager=True,
    )

    config = handler._get_agent_config()

    assert config.running.history_max_length == 1234
    assert observed == [("default", "tenant-a")]
```

- [ ] **Step 2: Add a constructor-level assertion for workspace wiring**

Append this test to `tests/unit/agents/test_memory_manager_tenant_scope.py`:

```python
def test_memory_manager_constructor_accepts_tenant_scope() -> None:
    manager = ReMeLightMemoryManager.__new__(ReMeLightMemoryManager)
    manager.agent_id = "default"
    manager.tenant_id = "tenant-a"

    assert manager.tenant_id == "tenant-a"
```

If you prefer stronger coverage, patch the workspace memory-manager factory path and assert the constructor receives `tenant_id="tenant-a"` from `Workspace._register_services`.

- [ ] **Step 3: Run guard tests**

Run: `venv/bin/python -m pytest tests/unit/agents/test_command_handler_tenant_scope.py tests/unit/agents/test_memory_manager_tenant_scope.py -q`

Expected: PASS.

- [ ] **Step 4: Commit the guard coverage**

```bash
git add tests/unit/agents/test_command_handler_tenant_scope.py tests/unit/agents/test_memory_manager_tenant_scope.py
git commit -m "test(runtime): guard tenant-scoped config reload paths"
```

### Task 5: Final Verification And Regression Sweep

**Files:**
- Test: `tests/unit/agents/test_source_tool_result_compact_config.py`
- Test: `tests/unit/agents/test_memory_manager_tenant_scope.py`
- Test: `tests/unit/agents/test_command_handler_tenant_scope.py`
- Test: `tests/unit/app/test_scheduled_run_source_system_config_binding.py`

- [ ] **Step 1: Run targeted regression suite**

Run: `venv/bin/python -m pytest tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_memory_manager_tenant_scope.py tests/unit/agents/test_command_handler_tenant_scope.py tests/unit/app/test_scheduled_run_source_system_config_binding.py -q`

Expected: PASS, and no test should observe `old_max_bytes=3000` when tenant-local `agent.json` is `50000`.

- [ ] **Step 2: Run one broader tenant/runtime suite**

Run: `venv/bin/python -m pytest tests/unit/app/test_agent_config_watcher.py tests/unit/agents/test_model_factory_tenant.py tests/unit/app/test_tenant_workspace.py -q`

Expected: PASS to confirm the tenant/runtime scope plumbing still behaves as expected.

- [ ] **Step 3: Inspect the final diff for scope-only changes**

Run: `git diff -- src/swe/agents/memory/base_memory_manager.py src/swe/agents/memory/reme_light_memory_manager.py src/swe/app/workspace/workspace.py src/swe/agents/hooks/memory_compaction.py src/swe/agents/command_handler.py tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_memory_manager_tenant_scope.py tests/unit/agents/test_command_handler_tenant_scope.py`

Expected: Only tenant-scope propagation, tenant-aware config loads, and regression tests.

- [ ] **Step 4: Commit the final verification checkpoint**

```bash
git add src/swe/agents/memory/base_memory_manager.py src/swe/agents/memory/reme_light_memory_manager.py src/swe/app/workspace/workspace.py src/swe/agents/hooks/memory_compaction.py src/swe/agents/command_handler.py tests/unit/agents/test_source_tool_result_compact_config.py tests/unit/agents/test_memory_manager_tenant_scope.py tests/unit/agents/test_command_handler_tenant_scope.py
git commit -m "fix(cron): honor tenant-scoped tool result compaction config"
```

## Spec Coverage Check

- Reported symptom coverage: `MemoryCompactionHook` now resolves tenant-local `tool_result_compact`, which directly addresses the observed cron compaction regression.
- Structural root-cause coverage: memory-manager instances now carry tenant scope, so adjacent config hot-reload reads no longer guess the scope.
- Adjacent hot-reload coverage: `CommandHandler` is included because it had the same unscoped read pattern and would otherwise remain a latent tenant bug.
- Source-system-config compatibility: existing scheduled-run source binding tests remain in the final verification suite to ensure the fix does not break request-level source overrides.

## Placeholder Scan

- No `TODO`/`TBD` markers remain.
- Every code-changing step includes exact files, code snippets, and commands.
- Every test step names the concrete test files to run.

## Type Consistency Check

- `tenant_id: str | None = None` is used consistently across `BaseMemoryManager`, `ReMeLightMemoryManager`, and `load_agent_config(...)`.
- The plan consistently assumes a single helper name: `ReMeLightMemoryManager._load_agent_config`.
- All regression assertions use the same expected tenant-side value: `old_max_bytes == 50000`.

