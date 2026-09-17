# Agent Trace `source_id` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export SWE's request source identity through the Agent Trace SDK root span and align every local SDK contract with the SDK 0.1.9 six-field schema.

**Architecture:** `AgentRunner.query_handler` continues to own the sole `agent.run` root span. It resolves `source_id` with the existing `_request_source_id()` helper, whose request → channel metadata → `"default"` precedence already matches the required contract. The fallback and test fake mirror the SDK's `TraceFields` schema; child spans inherit the root fields unchanged.

**Tech Stack:** Python 3.10+, pytest, AgentTraceSDK test fake, GitNexus.

---

### Task 1: Cover root-span source resolution

**Files:**
- Modify: `tests/unit/app/test_agent_trace_sdk.py:31-128`
- Modify: `src/swe/app/runner/runner.py:5215-5280`
- Modify: `tests/fakes/trace_sdk/_impl.py:24-30`

- [x] **Step 1: Add failing source-field assertions**

  In `test_query_handler_creates_one_server_root_span`, add
  `source_id="source-request"` to the `SimpleNamespace` request and assert:

  ```python
  assert root["trace_fields"]["source_id"] == "source-request"
  ```

  Add a second test with no `request.source_id`, a
  `channel_meta={"source_id": "source-meta"}`, and this assertion:

  ```python
  assert spans[0]["trace_fields"]["source_id"] == "source-meta"
  ```

  Add a third test with neither source location populated and this assertion:

  ```python
  assert spans[0]["trace_fields"]["source_id"] == "default"
  ```

  Change neither production code nor the fake before running this test.

- [x] **Step 2: Verify the tests fail for the missing trace field**

  Run:

  ```bash
  PYTHONPATH=tests/fakes /Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/app/test_agent_trace_sdk.py -q
  ```

  Expected: failure because the root span's serialized `trace_fields` has no
  `source_id` (or the fake rejects the new constructor argument after the
  production change is introduced).

- [x] **Step 3: Add the minimal root-field and fake-schema implementation**

  In the existing root-span construction, add only:

  ```python
  source_id=_request_source_id(request),
  ```

  after `agent_version=__version__`. Extend the fake dataclass with:

  ```python
  source_id: str
  ```

  after `agent_version`, preserving the documented SDK field order. Do not
  change source resolution or child-span construction.

- [x] **Step 4: Verify root-source behavior passes**

  Run the Step 2 command again.

  Expected: all root-span, schedule-skip, missing-required-field, admission,
  and retry-span tests pass.

### Task 2: Align the development fallback and direct fake users

**Files:**
- Modify: `tests/unit/tracing/test_agent_trace_sdk_fallback.py:28-64`
- Modify: `src/swe/tracing/agent_trace_sdk.py:31-42`
- Modify: `tests/unit/app/test_agent_trace_sdk.py:129-224`

- [x] **Step 1: Add a failing fallback contract test**

  Extend `_import_app_without_trace_sdk` with an optional Python suffix passed
  after `import swe.app._app`. Add a test that executes:

  ```python
  from swe.tracing.agent_trace_sdk import TraceFields

  fields = TraceFields(
      "task-1", "user-1", "session-1", "agent-1", "1.0", "source-a",
  )
  assert fields.source_id == "source-a"
  ```

  through the import-blocking subprocess with `allow_fallback=True`.

- [x] **Step 2: Verify the fallback test fails**

  Run:

  ```bash
  /Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/tracing/test_agent_trace_sdk_fallback.py -q
  ```

  Expected: the new subprocess exits non-zero because the fallback
  `TraceFields` accepts only five positional arguments.

- [x] **Step 3: Implement the fallback schema and update direct fake uses**

  Add `source_id: str` after `agent_version` in the fallback `TraceFields`
  dataclass. Update both direct fake constructors in
  `test_agent_trace_sdk.py` to pass `"source-1"` as their sixth positional
  value.

- [x] **Step 4: Verify fallback and child-span tests pass**

  Run:

  ```bash
  PYTHONPATH=tests/fakes /Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/app/test_agent_trace_sdk.py tests/unit/tracing/test_agent_trace_sdk_fallback.py -q
  ```

  Expected: all selected tests pass, including the fake-free subprocess
  fallback contract.

### Task 3: Declare the SDK floor and complete focused verification

**Files:**
- Modify: `pyproject.toml:50`
- Modify: `docs/superpowers/plans/2026-08-25-agent-trace-source-id.md`

- [x] **Step 1: Set the minimum SDK version**

  Replace the existing dependency literal with:

  ```toml
  "LR34.05-AgentTraceSDK>=0.1.9",
  ```

  This binds the declared distribution contract to the documented SDK version
  that requires `TraceFields.source_id`.

- [x] **Step 2: Run focused verification**

  Run:

  ```bash
  PYTHONPATH=tests/fakes /Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/app/test_agent_trace_sdk.py tests/unit/tracing/test_agent_trace_sdk_fallback.py -q
  git diff --check
  ```

  Expected: pytest reports no failures and `git diff --check` prints no
  whitespace errors.

- [x] **Step 3: Check changed-symbol scope and commit**

  Run `gitnexus detect_changes` in all-changes mode. Confirm that only the
  planned root-span, SDK-boundary, test fake, tests, dependency declaration,
  and this plan document are changed. Then commit the files with:

  ```bash
  git add pyproject.toml src/swe/app/runner/runner.py \\
    src/swe/tracing/agent_trace_sdk.py tests/fakes/trace_sdk/_impl.py \\
    tests/unit/app/test_agent_trace_sdk.py \\
    tests/unit/tracing/test_agent_trace_sdk_fallback.py \\
    docs/superpowers/plans/2026-08-25-agent-trace-source-id.md
  git commit -m "feat(tracing): add source id to agent trace"
  ```
