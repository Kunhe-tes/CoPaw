# Complexity Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the three specified orchestration functions to a cyclomatic complexity of at most 15 without changing their observable behavior.

**Architecture:** Keep each public or runtime-facing entry point as a thin orchestrator. Extract private helpers along existing responsibility boundaries: staged checkpoint actions, command-family dispatch, and evidence-query normalization/matching. Preserve the current lock lifetime, response ordering, exceptions, and external interfaces.

**Tech Stack:** Python 3.10+, pytest/pytest-asyncio, flake8 C901 complexity check, GitNexus impact analysis.

---

### Task 1: Isolate checkpoint-budget stage actions

**Files:**
- Modify: `tests/unit/agents/test_memory_compaction_checkpoint.py`
- Modify: `src/swe/agents/hooks/memory_compaction.py:MemoryCompactionHook._apply_checkpoint_budget_stage`

- [ ] **Step 1: Write a failing helper-boundary test**

Add a test that directly awaits a proposed `_install_checkpoint_stage` helper for an active decision and asserts it calls `install_ready_precompaction` and returns `False` after a remeasurement remains active:

```python
result = await hook._install_checkpoint_stage(
    agent, running, [], "chat-1", decision, AsyncMock(return_value=80)
)
assert result is False
```

- [ ] **Step 2: Verify the test fails because the helper does not exist**

Run: `venv/bin/python -m pytest tests/unit/agents/test_memory_compaction_checkpoint.py -k install_checkpoint_stage -q`

Expected: FAIL with `AttributeError` naming `_install_checkpoint_stage`.

- [ ] **Step 3: Extract budget-stage helpers**

Implement `_checkpoint_budget_context`, `_schedule_governance_precompaction`, `_install_checkpoint_stage`, and `_is_legacy_fallback_avoided`. Keep `_apply_checkpoint_budget_stage` responsible only for validation/context construction, decision calculation, and routing normal/governance/active/emergency. Retain the current task done-callback behavior, including clearing only the matching watermark on a false result or exception.

- [ ] **Step 4: Verify checkpoint behavior**

Run: `venv/bin/python -m pytest tests/unit/agents/test_memory_compaction_checkpoint.py -q`

Expected: PASS, including governance watermark deduplication, active remeasurement, and emergency degraded installation cases.

### Task 2: Split command-family handling from routing

**Files:**
- Modify: `tests/unit/app/test_daemon_restart_tenant_scope.py`
- Modify: `src/swe/app/runner/command_dispatch.py:run_command_path`

- [ ] **Step 1: Write a failing command-context helper test**

Add an async test that awaits a proposed `_resolve_command_context` helper with a request lacking `chat_id`, a runner chat manager, and session/user identifiers. Assert the returned context contains the lookup result and preserves the request channel:

```python
context = await command_dispatch._resolve_command_context(request, runner)
assert context.chat_id == "chat-1"
assert context.session_id == "session-1"
```

- [ ] **Step 2: Verify the test fails because the helper does not exist**

Run: `venv/bin/python -m pytest tests/unit/app/test_daemon_restart_tenant_scope.py -k resolve_command_context -q`

Expected: FAIL with `AttributeError` naming `_resolve_command_context`.

- [ ] **Step 3: Extract command handlers**

Add a private request-context dataclass and helpers `_resolve_command_context`, `_run_daemon_command`, `_run_control_command`, and `_run_conversation_command`. Each handler is an async iterator that yields the same `(Msg, True)` sequence as before. Keep `run_command_path` as query extraction plus daemon > control > conversation routing. Preserve session persistence and all existing error message text.

- [ ] **Step 4: Verify command behavior**

Run: `venv/bin/python -m pytest tests/unit/app/test_daemon_restart_tenant_scope.py tests/unit/app/test_runner_hook_runtime.py -q`

Expected: PASS, including tenant propagation, restart hint ordering, chat-id propagation, and runner command-stream integration.

### Task 3: Isolate evidence query preparation and matching

**Files:**
- Modify: `tests/unit/agents/test_chat_checkpoint_store.py`
- Modify: `src/swe/agents/memory/conversation_archive.py:ConversationArchiveStore._recover_evidence`

- [ ] **Step 1: Write a failing evidence-match helper test**

Add a test that builds a query with an exact reference plus incompatible semantic filters, then asserts a proposed `_matches_evidence_query` helper accepts the matching message. This records the exact-reference-precedence boundary:

```python
assert store._matches_evidence_query(
    message, requested={"message:1"}, semantic_query="miss", kind_filter={"user"}, time_bounds=None
)
```

- [ ] **Step 2: Verify the test fails because the helper does not exist**

Run: `venv/bin/python -m pytest tests/unit/agents/test_chat_checkpoint_store.py -k matches_evidence_query -q`

Expected: FAIL with `AttributeError` naming `_matches_evidence_query`.

- [ ] **Step 3: Extract evidence helpers**

Add an immutable private query object or normalization helper, `_matches_evidence_query`, and `_message_epoch_for_recovery`. Make `_recover_evidence` validate inputs, lock the chat, reject a mismatched epoch/empty lookup, and append only matching current-epoch messages until the existing capped limit is reached. Preserve legacy epoch-one fallback when `evidence-epochs.json` is absent.

- [ ] **Step 4: Verify evidence recovery behavior**

Run: `venv/bin/python -m pytest tests/unit/agents/test_chat_checkpoint_store.py tests/unit/agents/test_recover_evidence_tool.py -q`

Expected: PASS, including epoch isolation, legacy fallback, exact-reference precedence, semantic filter behavior, and tool error redaction.

### Task 4: Enforce complexity and review scope

**Files:**
- Modify: `src/swe/agents/hooks/memory_compaction.py`
- Modify: `src/swe/app/runner/command_dispatch.py`
- Modify: `src/swe/agents/memory/conversation_archive.py`

- [ ] **Step 1: Run the project complexity check**

Run: `venv/bin/python -m flake8 src/swe/agents/hooks/memory_compaction.py src/swe/app/runner/command_dispatch.py src/swe/agents/memory/conversation_archive.py --max-complexity=15 --select=C901`

Expected: PASS with no C901 findings.

- [ ] **Step 2: Run the focused regression suite**

Run: `venv/bin/python -m pytest tests/unit/agents/test_memory_compaction_checkpoint.py tests/unit/agents/test_chat_checkpoint_store.py tests/unit/agents/test_recover_evidence_tool.py tests/unit/app/test_daemon_restart_tenant_scope.py tests/unit/app/test_runner_hook_runtime.py -q`

Expected: PASS with no failures.

- [ ] **Step 3: Inspect formatting and impact scope**

Run: `venv/bin/python -m black --check src/swe/agents/hooks/memory_compaction.py src/swe/app/runner/command_dispatch.py src/swe/agents/memory/conversation_archive.py`

Run: `git diff --check`

Run: GitNexus `detect_changes({scope: "all"})`

Expected: formatting and whitespace checks pass; GitNexus reports only the intended modules and their directly affected runtime surfaces.
