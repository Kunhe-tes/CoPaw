# Goal Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first phase of the host-owned, durable Goal Runtime defined in `2026-08-22-goal-runtime-design.md`, including its Chat-facing controls and monitor.

**Architecture:** A new `src/swe/app/goals/` module owns strict Contract models, durable MySQL snapshots, lifecycle transitions, control-command precedence, incremental deterministic verification and in-request orchestration. The existing `AgentRunner` remains the sole Main Agent/tool runtime; a thin Goal adapter intercepts only Goal-mode turn boundaries. Console uses a distinct, compact monitor following `SubAgentRunMonitor`'s trigger/panel interaction model.

**Tech Stack:** Python 3.13, Pydantic, FastAPI, MySQL async connection, React 18, TypeScript, Ant Design, Vitest, pytest.

---

### Task 1: Define the independent Goal domain and prove lifecycle semantics

**Files:**
- Create: `src/swe/app/goals/models.py`
- Create: `src/swe/app/goals/service.py`
- Create: `tests/unit/app/goals/test_service.py`

- [ ] Write failing tests for strict Contract validation, exactly one non-terminal Goal per Chat, control precedence, revision activation, budget reset only on resume from `LIMITED`, and three same-criterion failures becoming `BLOCKED`.
- [ ] Implement immutable Goal Scope, revisioned Contract, criterion evidence, Goal snapshot, control commands, and narrow lifecycle service methods until those tests pass.
- [ ] Run `venv/bin/python -m pytest tests/unit/app/goals/test_service.py -q`.

### Task 2: Persist authoritative Goal snapshots in MySQL

**Files:**
- Create: `src/swe/app/goals/store.py`
- Create: `tests/unit/app/goals/test_store.py`

- [ ] Write failing store tests asserting idempotent schema creation, transactional snapshot/revision/criterion/control persistence, Chat-scope selection, and no audit-table creation.
- [ ] Implement the MySQL repository with the tables from the accepted design (`goals`, `goal_revisions`, `goal_criteria`, `goal_steering`, `goal_subagent_links`, `goal_control_commands`) and read projections used by the service.
- [ ] Run `venv/bin/python -m pytest tests/unit/app/goals/test_store.py -q`.

### Task 3: Integrate Goal entry, Main Agent turn settlement, verification, and APIs

**Files:**
- Create: `src/swe/app/goals/runtime.py`
- Create: `src/swe/app/goals/router.py`
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/agents/react_agent.py`
- Modify: `src/swe/agents/tools/planning.py`
- Modify: `src/swe/app/routers/agent_scoped.py`
- Test: `tests/unit/app/goals/test_runtime.py`
- Test: `tests/unit/app/goals/test_router.py`
- Test: `tests/unit/agents/tools/test_planning.py`

- [ ] Write failing tests for Goal-ready Proposal creation, Contract confirmation, structured turn resolution, automatic continuation without ordinary stream completion, verification gating, safe finalization, steering, and all control endpoints.
- [ ] Implement only the adapter hooks necessary to run normal Main Agent turns under Goal Runtime, run read-only Contract-bound verification through the existing guard path, and expose scoped snapshot/pause/resume/cancel/edit APIs.
- [ ] Run `venv/bin/python -m pytest tests/unit/app/goals tests/unit/agents/tools/test_planning.py -q`.

### Task 4: Add the Console Goal entry, Contract editor, and monitor

**Files:**
- Create: `console/src/pages/Chat/components/GoalMonitor/index.tsx`
- Create: `console/src/pages/Chat/components/GoalMonitor/index.module.less`
- Create: `console/src/pages/Chat/components/GoalMonitor/index.test.tsx`
- Modify: `console/src/api/modules/chat.ts`
- Modify: `console/src/api/types/chat.ts`
- Modify: `console/src/pages/Chat/index.tsx`
- Modify: the existing Plan interaction card component(s) that render `submit_proposed_plan`

- [ ] Write failing API and component tests for compact trigger/panel behavior, recent Goal selection, state/criteria summary, action availability, action errors, and full Contract direct edit.
- [ ] Implement the Goal-specific monitor using the established SubAgent Monitor interaction rhythm, add direct Goal Mode / Contract confirmation integration, and preserve the existing chat timeline semantics.
- [ ] Run `pnpm test:run src/pages/Chat/components/GoalMonitor/index.test.tsx src/api/modules/chatSubagents.test.ts` from `console/`.

### Task 5: Verify, review, and commit

**Files:**
- Modify: `CONTEXT.md` only if implementation reveals a terminology correction
- Modify: `docs/superpowers/specs/2026-08-22-goal-runtime-design.md` only if implementation reveals an accepted design correction

- [ ] Run focused backend tests, then the relevant Console tests, typecheck/lint/build, and `pre-commit` on changed files.
- [ ] Run GitNexus `detect_changes` and inspect every affected execution flow.
- [ ] Dispatch an independent code-review subagent, verify each reported finding against source and tests, and fix valid issues.
- [ ] Commit only Goal Runtime files and their tests with `git commit --only` so unrelated user changes remain untouched.
