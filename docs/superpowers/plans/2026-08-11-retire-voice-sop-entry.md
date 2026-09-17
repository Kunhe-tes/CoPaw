# Retire Voice SOP Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete voice-generated W+ SOP entry and restore regression coverage for console chat identity rejection.

**Architecture:** The voice recorder becomes transcription-only by deleting the control that replaces a chat draft with an obsolete skill mention. The console chat route keeps its existing validation helper; focused route tests will verify that validation rejects mismatched user and agent identities before any work is started.

**Tech Stack:** React, TypeScript, Vitest, FastAPI, pytest.

---

### Task 1: Remove the obsolete voice SOP action

**Files:**

- Modify: `console/src/components/GlobalVoiceRecorder/index.tsx:1-76, 258-276`
- Modify: `console/src/components/GlobalVoiceRecorder/index.test.tsx:1-18, 170-243`
- Delete: `console/src/components/GlobalVoiceRecorder/sop.ts`
- Delete: `console/src/components/GlobalVoiceRecorder/sop.test.ts`

- [ ] **Step 1: Write the failing UI expectation**

  Replace the existing SOP-generation expectation with a test that requires the ready recorder to omit the retired control:

  ```tsx
  expect(
    screen.queryByRole("button", { name: "生成SOP" }),
  ).not.toBeInTheDocument();
  ```

- [ ] **Step 2: Run the targeted test to verify it fails**

  Run:

  ```bash
  pnpm exec vitest run src/components/GlobalVoiceRecorder/index.test.tsx
  ```

  Expected: FAIL because the `生成SOP` button is still rendered.

- [ ] **Step 3: Delete the retired behaviour**

  In `index.tsx`, remove `ProfileOutlined`, `emitChatInputReplaceText`, and
  `buildVoiceSopPrompt` imports; remove `handleGenerateSop`; and remove the
  button whose `aria-label` is `生成SOP`. Delete `sop.ts` and `sop.test.ts`.
  Keep `onTranscriptionSuccess` and `emitChatInputAppendText` unchanged.

- [ ] **Step 4: Run the targeted test to verify it passes**

  Run:

  ```bash
  pnpm exec vitest run src/components/GlobalVoiceRecorder/index.test.tsx
  ```

  Expected: PASS, with no rendered SOP action and existing transcription tests green.

- [ ] **Step 5: Commit the voice cleanup**

  ```bash
  git add console/src/components/GlobalVoiceRecorder
  git commit -m "fix(voice): remove obsolete sop action"
  ```

### Task 2: Restore console identity rejection tests

**Files:**

- Modify: `tests/unit/routers/test_console_chat_stream.py:1-66, after test_console_chat_stream_emits_keepalive_and_disables_proxy_buffering`
- Modify: `src/swe/app/routers/console.py:924-953` only if the new route tests reveal a defect

- [ ] **Step 1: Write failing sender-mismatch and agent-mismatch route tests**

  Add a client builder that mounts `console_router.router`, returns a workspace
  with `_FakeChannelManager`, `_FakeChatManager`, and `_FakeTaskTracker`, and
  sets `request.state.user_id` / `request.state.agent_id` in a test middleware.
  The first test posts `user_id="victim-user"` while middleware supplies
  `user_id="authenticated-user"`; the second posts with matching user ID while
  workspace has `agent_id="workspace-agent"` and middleware supplies
  `agent_id="authenticated-agent"`. Both send `X-Source-Id` and assert:

  ```python
  assert response.status_code == 403
  assert response.json()["detail"] == expected_detail
  ```

- [ ] **Step 2: Run the two tests to capture the existing guarded behaviour**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py \
    -k "authenticated_user_mismatch or authenticated_agent_mismatch" -q
  ```

  Expected: PASS. This task adds coverage for existing production validation,
  so the new tests should immediately demonstrate the two preserved 403 rules.

- [ ] **Step 3: Keep the production boundary unchanged**

  Do not alter production validation unless Step 2 exposes a discrepancy.
  `_validate_console_chat_identity` must continue to return 403 before
  `_start_new_chat` or `_attach_reconnect_queue` is reached.

- [ ] **Step 4: Run focused backend tests to verify they pass**

  Run:

  ```bash
  venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py \
    tests/unit/routers/test_agents_tenant_scope.py -q
  ```

  Expected: PASS, including both identity-rejection tests.

- [ ] **Step 5: Commit the regression coverage**

  ```bash
  git add tests/unit/routers/test_console_chat_stream.py
  git commit -m "test(console): cover chat identity validation"
  ```

### Task 3: Final merge-safety verification

**Files:**

- Verify: `console/src/components/GlobalVoiceRecorder/index.tsx`
- Verify: `tests/unit/routers/test_console_chat_stream.py`

- [ ] **Step 1: Run the affected frontend and backend tests together**

  ```bash
  pnpm exec vitest run src/components/GlobalVoiceRecorder/index.test.tsx
  venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py \
    tests/unit/routers/test_agents_tenant_scope.py -q
  ```

  Expected: all selected tests pass.

- [ ] **Step 2: Check the final change scope**

  ```bash
  git diff --check
  git status --short
  ```

  Expected: no whitespace errors; only the voice cleanup and console test
  coverage changes are newly introduced.
