# Console Plan Mode Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the frontend's validated `mode` request field through the Console adapter so the first Plan Mode request registers `ask_plan_clarification` and injects the Plan Mode prompt.

**Architecture:** Keep the existing frontend request contract and Runner mode resolution unchanged. Extend the Console router's existing allowlisted payload extraction to copy only `plan`/`normal` into `native_payload.meta`; the Console channel and Runner will then use their existing `channel_meta` path.

**Tech Stack:** Python, FastAPI/Pydantic request adapter, pytest.

---

### Task 1: Lock the Console boundary contract with tests

**Files:**
- Modify: `tests/unit/app/test_console_chat_file_url_network.py`
- Test: `tests/unit/app/test_console_chat_file_url_network.py`

- [ ] **Step 1: Add a test for plan mode propagation**

  Call `_extract_session_and_payload()` with a Console-shaped mapping containing `mode: "plan"` and assert the returned `meta.mode` is `"plan"`.

- [ ] **Step 2: Add a test for normal mode propagation and invalid-value filtering**

  Assert `mode: "normal"` is retained and an unsupported value is absent from the returned metadata.

- [ ] **Step 3: Run the focused tests and verify RED**

  Run: `venv/bin/python -m pytest tests/unit/app/test_console_chat_file_url_network.py -q`

  Expected: the new mode propagation assertions fail because the current adapter drops `mode`.

### Task 2: Implement the minimal adapter fix

**Files:**
- Modify: `src/swe/app/routers/console.py:618-632, 788-814`

- [ ] **Step 1: Extract a validated mode from the incoming mapping/request metadata**

  Preserve only `"plan"` and `"normal"`; treat missing or invalid values as `None`.

- [ ] **Step 2: Add the validated mode to `native_payload.meta`**

  Do not alter frontend fields, Runner resolution, persistence, or other metadata behavior.

- [ ] **Step 3: Run the focused tests and verify GREEN**

  Run: `venv/bin/python -m pytest tests/unit/app/test_console_chat_file_url_network.py -q`

  Expected: all tests pass.

### Task 3: Verify the complete Plan Mode seam

**Files:**
- No additional production files.

- [ ] **Step 1: Run Console boundary and Runner state tests**

  Run: `venv/bin/python -m pytest tests/unit/app/test_console_chat_file_url_network.py tests/unit/app/test_runner_plan_mode_state.py -v`

- [ ] **Step 2: Run the Agent toolkit and prompt regression tests**

  Run: `venv/bin/python -m pytest tests/unit/subagents/test_react_agent_and_guard_integration.py tests/unit/app/test_task_progress_switch.py -q`

- [ ] **Step 3: Inspect the final diff and run GitNexus change detection if available**

  Confirm only the Console adapter and its focused tests changed; report any unrelated worktree changes separately.
