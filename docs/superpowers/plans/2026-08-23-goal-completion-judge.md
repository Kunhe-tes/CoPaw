# Goal Completion Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace command-only Goal verification with independent natural-language Completion Judge review while preserving lifecycle, budget, approval, and revision safety.

**Architecture:** GoalRuntime keeps state authority while accepting a completion-review callback. AgentRunner creates a separate frozen-model `SWEAgent` with a `completion_judge` role, a bounded review package and a readonly builtin-tool allowlist.

**Tech Stack:** Python, Pydantic, AgentScope `SWEAgent`, existing Tool Guard/Approval service, pytest.

---

### Task 1: Model completion review in GoalRuntime

**Files:**

- Modify: `src/swe/app/goals/runtime.py`
- Modify: `src/swe/app/goals/service.py`
- Test: `tests/unit/app/goals/test_runtime.py`

- [x] Write failing tests showing natural-language completion can pass only when `reviewer` accepts, and evidence-insufficiency rejects block after three attempts.

```python
runtime = GoalRuntime(
    service,
    reviewer=lambda _: {"criterion-1": (False, "Missing test output")},
)
for _ in range(3):
    result = await runtime.settle(goal.goal_id, completion_resolution())
assert result.state == GoalState.BLOCKED
assert "review rejected" in (result.state_reason or "")
```

- [x] Run `venv/bin/python -m pytest tests/unit/app/goals/test_runtime.py -q`; expect red because `reviewer` does not exist.
- [x] Introduce `CompletionReviewResult`, `CompletionReviewPending`, and `CompletionReviewer`; rename callback use, logs and state reasons. Retain persisted `verified`, `consecutive_failures`, `evidence_refs`, and `verification_request_id` names for compatibility.
- [x] Run the same command; expect green.
- [x] Commit only runtime/service/tests: `refactor(goals): model completion review outcomes`.

### Task 2: Add restricted Completion Judge role

**Files:**

- Modify: `src/swe/agents/react_agent.py`
- Modify: `src/swe/app/runner/runner.py`
- Test: `tests/unit/app/test_runner_goal_lifecycle.py`

- [x] Write a failing test that calls `_create_goal_completion_judge_agent` and asserts `agent_role == "completion_judge"`, frozen resolved model/provider, no memory/MCP/skills/SubAgent/Plan/Goal-control tools, and only `read_file`, `grep_search`, `glob_search`, and `get_current_time` at most.
- [x] Run `venv/bin/python -m pytest tests/unit/app/test_runner_goal_lifecycle.py -q`; expect red because no Judge factory exists.
- [x] Add a role branch that denies all tools outside the readonly allowlist and skips Main-Agent tool registration. Add a factory beside finalization-agent construction that passes only Tool-Guard correlation identity, disables memory/workspace skills/MCP/source tools/SubAgents and uses a fixed Judge prompt.
- [x] Run the same lifecycle suite; expect green.
- [x] Commit only Agent/runner/tests: `feat(goals): add restricted completion judge`.

### Task 3: Add bounded review protocol and fail-closed parsing

**Files:**

- Create: `src/swe/app/goals/review.py`
- Modify: `src/swe/app/runner/runner.py`
- Test: `tests/unit/app/goals/test_review.py`
- Test: `tests/unit/app/test_runner_goal_lifecycle.py`

- [x] Write failing tests for parsing one `accept`/`reject` decision per requested criterion, and reject all unresolved criteria for malformed JSON, duplicate, unknown or missing IDs.

```python
parsed = parse_completion_review(
    '{"reviews":[{"criterion_id":"criterion-1","decision":"accept","reason":"Observed output","evidence_refs":["tool-1"]}]}',
    {"criterion-1"},
)
assert parsed["criterion-1"] == (True, "Observed output")
```

- [x] Run `venv/bin/python -m pytest tests/unit/app/goals/test_review.py -q`; expect red because the module does not exist.
- [x] Implement bounded review input containing only Contract/Revision, selected Criteria, Main-Agent proposal/evidence, and relevant current-turn tool observations. Parse Judge JSON fail-closed; never expose Judge output to Chat or Main-Agent memory.
- [x] Add a runner callback that calls the Judge and parses its final response.
- [x] Run `venv/bin/python -m pytest tests/unit/app/goals/test_review.py tests/unit/app/test_runner_goal_lifecycle.py -q`; expect green.
- [x] Commit review module/runner/tests: `feat(goals): judge natural language completion criteria`.

### Task 4: Integrate approval wakes and incremental review

**Files:**

- Modify: `src/swe/app/goals/runtime.py`
- Modify: `src/swe/app/runner/runner.py`
- Test: `tests/unit/app/goals/test_runtime.py`
- Test: `tests/unit/app/test_runner_goal_lifecycle.py`

- [x] Write failing tests for a Judge Tool-Guard approval entering `WAITING`, retrying the same selected criteria without another Main-Agent turn, and a denied approval recording one rejection.
- [x] Run `venv/bin/python -m pytest tests/unit/app/goals/test_runtime.py tests/unit/app/test_runner_goal_lifecycle.py -q`; expect red.
- [x] Return `CompletionReviewPending` from `judge._tool_guard_pending_info`; on retry use approval status/replay semantics, preserve subset, and map denial to a rejection reason.
- [x] Preserve existing selection: environment writes review affected criteria (or all when omitted); `propose_completion` reviews all unaccepted criteria; Direct Goal Edit winning settlement prevents old-Revision review.
- [x] Run `venv/bin/python -m pytest tests/unit/app/goals tests/unit/app/test_runner_goal_lifecycle.py -q`; expect green.
- [x] Commit runtime/runner/tests: `feat(goals): resume pending completion reviews`.

### Task 5: Independent review and final verification

**Files:**

- Modify: `CONTEXT.md`
- Modify: `docs/superpowers/specs/2026-08-23-goal-completion-judge-design.md`
- Test: `tests/unit/app/goals/`
- Test: `tests/unit/app/test_runner_goal_lifecycle.py`

- [x] Reconcile documentation only with final behavior.
- [x] Launch an independent reviewer with the approved spec and final diff; require severity, file/line evidence and missing-test analysis.
- [x] For each accepted finding, write a focused red test, make the minimum fix, and rerun the relevant suite.
- [x] Run `venv/bin/python -m pytest tests/unit/app/goals tests/unit/app/test_runner_goal_lifecycle.py -q`, `venv/bin/python -m py_compile src/swe/app/goals/runtime.py src/swe/app/goals/review.py src/swe/app/runner/runner.py`, and `git diff --check`; expect all zero.
- [x] Run GitNexus `detect_changes(scope="staged")`, inspect expected Goal scope, and commit any final scoped fixes.
