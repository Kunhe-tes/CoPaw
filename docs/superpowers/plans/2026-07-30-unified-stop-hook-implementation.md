# Unified Stop Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `BeforeStop` and observation-only `Stop` with a single blockable `Stop` completion event, including its System Configuration UI and repository examples.

**Architecture:** The hook runtime treats `Stop` as the only completion-gate event and preserves its merged result. The runner consumes that result once per candidate assistant response, retries only an explicit block, and ends incomplete on a blocking handler failure. The console and examples expose `Stop` only.

**Tech Stack:** Python 3.11, Pydantic, pytest, React, TypeScript, Vitest, pnpm.

---

### Task 1: Make Stop the sole validated completion-gate event

**Files:**
- Modify: `src/swe/agents/hook_runtime/models.py`
- Modify: `src/swe/agents/hook_runtime/output.py`
- Modify: `src/swe/agents/hook_runtime/executor.py`
- Modify: `src/swe/agents/hook_runtime/runtime.py`
- Test: `tests/unit/agents/hook_runtime/test_models_resolver.py`
- Test: `tests/unit/agents/hook_runtime/test_handlers_and_merge.py`

- [ ] **Step 1: Write the failing validation and result-propagation tests.**

```python
def test_before_stop_is_rejected_from_hook_config() -> None:
    with pytest.raises(ValidationError):
        HookConfig.model_validate({"enabled": True, "events": {"BeforeStop": []}})

def test_stop_output_accepts_only_allow_or_block() -> None:
    assert normalize_hook_output(..., event_name=HookEventName.STOP).decision == HookDecision.ALLOW
    with pytest.raises(ValueError, match="Stop hook output"):
        normalize_hook_output(..., raw_output={"decision": "stop"}, event_name=HookEventName.STOP)

async def test_runtime_stop_returns_merged_gate_result(...) -> None:
    assert (await runtime.emit(_context(HookEventName.STOP), workspace_dir=tmp_path)).decision == HookDecision.BLOCK
```

- [ ] **Step 2: Run the focused tests.** Run `../../venv/bin/python -m pytest tests/unit/agents/hook_runtime/test_models_resolver.py tests/unit/agents/hook_runtime/test_handlers_and_merge.py -q`. Expected: newly added assertions fail because BeforeStop exists and Stop is observation-only.
- [ ] **Step 3: Implement the minimum runtime migration.** Remove `BEFORE_STOP` from `HookEventName`; make Stop validation reject any decision other than `allow`/`block` and all non-gate output fields; apply the same prompt constraint in `executor.py`; remove the runtime branch that erases Stop results.
- [ ] **Step 4: Re-run the focused tests.** Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add src/swe/agents/hook_runtime tests/unit/agents/hook_runtime && git commit -m "feat(hooks): make stop the completion gate"`.

### Task 2: Consume unified Stop decisions in the runner

**Files:**
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/config/config.py`
- Modify: `src/swe/agents/hook_runtime/models.py`
- Modify: `src/swe/agents/hook_runtime/merge.py`
- Test: `tests/unit/app/test_runner_hook_runtime.py`
- Test: `tests/unit/config/test_agents_running_config_llm_workloads.py`

- [ ] **Step 1: Write failing lifecycle tests.**

```python
async def test_stop_block_retries_then_allows(...) -> None:
    # fake Stop returns BLOCK and then ALLOW
    assert stop_calls == 2
    assert [item[0].get_text_content() for item in outputs] == ["agent reply", "agent reply"]

async def test_stop_blocking_handler_failure_finishes_incomplete(...) -> None:
    # a Stop result with a blocking failed handler produces no second agent turn
    assert agent_call_count == 1
    assert outputs[-1][0].get_text_content().startswith("任务未完成：")
```

- [ ] **Step 2: Run `../../venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py -q`.** Expected: newly added unified Stop assertions fail.
- [ ] **Step 3: Implement the runner migration.** Replace both old runner emitters with one Stop emitter guarded by a candidate assistant response. Rename all before-stop counters/messages/configuration to stop. Add a `has_blocking_failure` field to `MergedHookResult` and set it in `merge_hook_results`; only `decision == BLOCK` without that flag schedules a follow-up. A blocking failure sets the existing incomplete outcome and yields its reason.
- [ ] **Step 4: Run runner/config tests.** Run `../../venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py tests/unit/config/test_agents_running_config_llm_workloads.py -q`. Expected: PASS; terminal tool-hook stop remains skipped.
- [ ] **Step 5: Commit.** Run `git add src/swe/app/runner/runner.py src/swe/config/config.py src/swe/agents/hook_runtime/models.py src/swe/agents/hook_runtime/merge.py tests/unit/app/test_runner_hook_runtime.py tests/unit/config/test_agents_running_config_llm_workloads.py && git commit -m "feat(runner): gate completion with stop hooks"`.

### Task 3: Remove BeforeStop from System Configuration

**Files:**
- Modify: `console/src/pages/Control/HookManagement/types.ts`
- Modify: `console/src/pages/Control/HookManagement/eventMetadata.ts`
- Modify: `console/src/pages/Control/HookManagement/index.tsx`
- Test: `console/src/pages/Control/HookManagement/overviewModel.test.ts`

- [ ] **Step 1: Change the overview test before implementation.**

```tsx
expect(getLifecycleEvents({ enabled: true, events: {} })).toEqual([
  "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
  "PostToolUseFailure", "Stop",
]);
expect(getEventSummary({ enabled: true, events: {} }, "Stop")).toMatchObject({ configured: false });
```

- [ ] **Step 2: Run `pnpm --dir console test:run src/pages/Control/HookManagement/overviewModel.test.ts`.** Expected: FAIL because BeforeStop remains listed.
- [ ] **Step 3: Remove the obsolete union member, metadata item, and array entry.** Give Stop the description `在候选回复完成前触发，可记录并批准或阻断完成。` with order 6. Do not map legacy event names.
- [ ] **Step 4: Run `pnpm --dir console test:run src/pages/Control/HookManagement/overviewModel.test.ts && pnpm --dir console exec tsc -b --noEmit`.** Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add console/src/pages/Control/HookManagement && git commit -m "feat(console): expose unified stop hook"`.

### Task 4: Migrate configurations, examples, and tests

**Files:**
- Modify: every hook fixture and test identified by `rg -n 'BeforeStop|before_stop|before-stop' tests wiki/hook src console`
- Modify: `wiki/hook/README.md`, `wiki/hook/hook-runtime.md`, and `wiki/hook/customer-hook-demo-guide.md`

- [ ] **Step 1: Add a failing fixture test that loads each converted Stop configuration and asserts no BeforeStop event is accepted.**
- [ ] **Step 2: Run `../../venv/bin/python -m pytest tests/unit/agents/hook_runtime tests/unit/app/test_hook_management.py -q`.** Expected: failures identify configurations, test names, and documentation scripts that still use BeforeStop.
- [ ] **Step 3: Convert all event keys and HookContext payloads to Stop.** Rename user-facing demo/script names containing BeforeStop; change the former observation-only Stop example to return `{"decision": "allow", "reason": "..."}`; document Stop as the bounded completion gate and its `max_stop_turns` budget.
- [ ] **Step 4: Re-run the focused Python suite and `rg -n 'BeforeStop|before_stop|before-stop' src console tests wiki/hook`.** Expected: tests pass and the search has no functional stale references.
- [ ] **Step 5: Commit.** Run `git add wiki/hook tests && git commit -m "docs(hooks): migrate completion examples to stop"`.

### Task 5: Verification and independent review

**Files:** Modify only when review identifies a defect.

- [ ] **Step 1: Run the full focused matrix.** Run `../../venv/bin/python -m pytest tests/unit/agents/hook_runtime tests/unit/app/test_runner_hook_runtime.py tests/unit/app/test_hook_management.py tests/unit/config/test_hook_config_models.py tests/unit/config/test_agents_running_config_llm_workloads.py -q && pnpm --dir console test:run src/pages/Control/HookManagement/overviewModel.test.ts && pnpm --dir console exec tsc -b --noEmit`. Expected: PASS.
- [ ] **Step 2: Run stale-name and whitespace checks.** Run `rg -n 'BeforeStop|before_stop|before-stop' src console tests wiki/hook || true && git diff main...HEAD --check`. Expected: no functional stale-name matches or whitespace errors.
- [ ] **Step 3: Run GitNexus `detect_changes({scope: "compare", base_ref: "main"})` and review every changed execution flow.**
- [ ] **Step 4: Dispatch an independent code-review subagent.** Fix every finding, re-run its focused verification, and commit each correction with `fix(hooks): address review findings`.
