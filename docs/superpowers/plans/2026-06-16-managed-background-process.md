# Managed Background Process Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add source-scoped managed background shell processes that can be started, listed, inspected, and stopped across turns in one backend runtime.

**Architecture:** Reuse `execute_shell_command` preparation for command normalization, tenant-aware `cwd`, explicit path boundary validation, runtime env, and Python runtime path guarding. Add an in-memory manager in `src/swe/agents/tools/background_process.py` keyed by source/tenant/user/chat/agent/workspace owner context, backed by `subprocess.Popen` with temp-file output capture and best-effort process-tree cleanup.

**Tech Stack:** Python, AgentScope `ToolResponse`, pytest, FastAPI lifespan shutdown, existing Swe Tool Guard YAML rules.

---

### Task 1: Share Shell Command Preparation

**Files:**
- Modify: `src/swe/agents/tools/shell.py`
- Test: `tests/unit/test_shell_tenant_boundary.py`

- [ ] **Step 1: Write the failing test**

Add a test that imports `prepare_shell_command` and proves it returns the intercepted command, resolved cwd, env, and a usable runtime guard:

```python
with tenant_context(tenant_id="test_tenant", workspace_dir=tenant_dir):
    prepared = prepare_shell_command("echo ok", cwd=str(tenant_dir))
assert prepared.command == "echo ok"
assert prepared.working_dir == tenant_dir.resolve()
assert "PATH" in prepared.env
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_shell_tenant_boundary.py -k prepare_shell_command -v`
Expected: FAIL because `prepare_shell_command` is not exported yet.

- [ ] **Step 3: Implement shared helper**

Add `PreparedShellCommand` and `prepare_shell_command()` to `shell.py`. Move the current `execute_shell_command` preparation sequence into the helper without changing behavior:

```python
@dataclass(frozen=True)
class PreparedShellCommand:
    command: str
    working_dir: Path
    env: dict[str, str]
    python_runtime_guard: AbstractContextManager[None]


def prepare_shell_command(command: str, cwd: Optional[Path | str] = None) -> PreparedShellCommand:
    ...
```

- [ ] **Step 4: Refactor `execute_shell_command` to use helper**

Keep response and error semantics identical; only replace inline preparation with `prepared = prepare_shell_command(command, cwd)`.

- [ ] **Step 5: Verify shell tests**

Run: `python -m pytest tests/unit/test_shell_tenant_boundary.py -v`
Expected: PASS.

### Task 2: Add Background Process Manager And Tools

**Files:**
- Create: `src/swe/agents/tools/background_process.py`
- Create: `tests/unit/agents/tools/test_background_process.py`

- [ ] **Step 1: Write failing owner and lifecycle tests**

Cover short command output, running process stop, owner isolation by `source_id`, bounded output, and process limits.

```python
with tenant_context(tenant_id="tenant_a", user_id="user_a", source_id="source_a", workspace_dir=workspace):
    result = await start_background_process(command, name="demo")
    processes = await list_background_processes()
    output = await get_process_output(process_id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/agents/tools/test_background_process.py -v`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement data model and owner key**

Create `BackgroundProcessOwnerKey`, `ManagedBackgroundProcess`, and `ManagedBackgroundProcessManager`. Owner key fields are `source_id`, `scope_id`, `tenant_id`, `user_id`, `chat_id`, `agent_id`, and `workspace_dir`. Use explicit fallback strings only when context values are absent.

- [ ] **Step 4: Implement start/list/output/stop tools**

Use `prepare_shell_command`. Launch with `cmd.exe /D /S /C <command>` on Windows and `/bin/sh -c <command>` on Unix. Capture stdout/stderr to temp files, close parent handles after spawn, and do not expose temp paths in tool output.

- [ ] **Step 5: Implement cleanup and pruning**

Add per-owner and global running limits, terminal-record retention pruning, temp-file cleanup, `stop_all()`, and `register_atexit_cleanup()`.

- [ ] **Step 6: Verify background-process tests**

Run: `python -m pytest tests/unit/agents/tools/test_background_process.py -v`
Expected: PASS.

### Task 3: Register Tools, Summaries, And Tool Guard

**Files:**
- Modify: `src/swe/agents/tools/__init__.py`
- Modify: `src/swe/agents/react_agent.py`
- Modify: `src/swe/config/config.py`
- Modify: `src/swe/agents/utils/tool_summary.py`
- Modify: `src/swe/security/tool_guard/rules/dangerous_shell_commands.yaml`
- Test: `tests/unit/agents/test_tool_failure.py`
- Test: `tests/unit/agents/test_tool_summary.py`
- Test: `tests/unit/app/test_database_access_guard.py`

- [ ] **Step 1: Write failing registration and guard tests**

Assert `_create_toolkit()` contains all four new tools by default and that a shell rule matching `execute_shell_command` also matches `start_background_process`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/agents/test_tool_failure.py tests/unit/agents/test_tool_summary.py tests/unit/app/test_database_access_guard.py -v`
Expected: FAIL on missing registrations/rule coverage.

- [ ] **Step 3: Wire built-ins**

Import/export tools, add default `BuiltinToolConfig` entries, and register them in `SWEAgent._create_toolkit` as normal built-ins with `async_execution=False`.

- [ ] **Step 4: Wire safe summaries and Tool Guard rules**

Treat `start_background_process` as shell-sensitive for call/output redaction. Update active shell rules to include both `execute_shell_command` and `start_background_process`.

- [ ] **Step 5: Verify registration and guard tests**

Run: `python -m pytest tests/unit/agents/test_tool_failure.py tests/unit/agents/test_tool_summary.py tests/unit/app/test_database_access_guard.py -v`
Expected: PASS.

### Task 4: Shutdown Cleanup

**Files:**
- Modify: `src/swe/app/_app.py`
- Test: `tests/unit/agents/tools/test_background_process.py`

- [ ] **Step 1: Write failing shutdown test**

Assert `managed_background_process_manager.stop_all()` terminates running records and removes temp files.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/agents/tools/test_background_process.py -k stop_all -v`
Expected: FAIL until cleanup is implemented.

- [ ] **Step 3: Add lifecycle cleanup**

Call `managed_background_process_manager.stop_all()` in FastAPI lifespan shutdown before final `Application shutdown complete` logging.

- [ ] **Step 4: Final verification**

Run:

```powershell
python -m pytest tests/unit/agents/tools/test_background_process.py -v
python -m pytest tests/unit/test_shell_tenant_boundary.py -v
python -m pytest tests/unit/agents/test_tool_failure.py tests/unit/agents/test_tool_summary.py tests/unit/app/test_database_access_guard.py -v
```

Expected: all selected tests pass.
