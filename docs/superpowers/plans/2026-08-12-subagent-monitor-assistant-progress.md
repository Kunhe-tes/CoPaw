# Assistant Monitor Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show chat-facing Background SubAgent Runs as assistants with truthful time and turn budgets, collapsible terminal results, and prompt post-start visibility.

**Architecture:** The persisted background-run record gains a runtime-owned `turns_used` observation. The monitor snapshot exposes it with the effective `max_turns`, while the terminal result remains authoritative after completion. The React monitor keeps its compact floating trigger, renders terminal summaries behind per-row disclosure controls, and performs an immediate plus delayed-confirmation refresh for SubAgent SSE hints.

**Tech Stack:** Python 3.13, Pydantic, FastAPI, React 18, TypeScript, Vitest, Testing Library.

---

### Task 1: Persist and project live turn progress

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/run_store.py`
- Modify: `src/swe/app/subagents/runtime.py`
- Modify: `src/swe/app/subagents/monitor.py`
- Test: `tests/unit/subagents/test_monitor_api.py`

- [ ] **Step 1: Write failing snapshot tests**

```python
assert running["budget_consumption"] == {
    "elapsed_ms": mock.ANY,
    "timeout_ms": 120_000,
    "turns_used": 2,
    "max_turns": 4,
    "ratio": mock.ANY,
}
assert completed["budget_consumption"]["turns_used"] == 3
```

- [ ] **Step 2: Run the targeted test and verify it fails because the new fields are absent**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_monitor_api.py -q`
Expected: FAIL with missing `turns_used` / `max_turns` assertions.

- [ ] **Step 3: Add minimal runtime observation and snapshot projection**

```python
class BackgroundSubAgentRunRecord(BaseModel):
    turns_used: int = 0

def _budget_consumption(record):
    terminal_turns = record.result.metrics.turns_used if record.result else None
    return SubAgentBudgetConsumption(
        ...,
        turns_used=terminal_turns if terminal_turns is not None else record.turns_used,
        max_turns=record.effective_budget.max_turns,
    )
```

Update the research progress callback to persist each observed turn, without changing the start/cancel API contract.

- [ ] **Step 4: Re-run the monitor API tests**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_monitor_api.py -q`
Expected: PASS.

### Task 2: Render assistants, dual budgets, and collapsed terminal results

**Files:**
- Modify: `console/src/api/types/chat.ts`
- Modify: `console/src/pages/Chat/components/SubAgentRunMonitor/index.tsx`
- Modify: `console/src/pages/Chat/components/SubAgentRunMonitor/index.module.less`
- Test: `console/src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx`

- [ ] **Step 1: Write failing component tests**

```tsx
expect(screen.getByRole("button", { name: "助手运行状态" })).toBeInTheDocument();
expect(screen.getByText("已用时间 30s / 2m")).toBeInTheDocument();
expect(screen.getByText("已用轮次 2 / 4")).toBeInTheDocument();
expect(screen.queryByText("已完成的结果摘要")).toBeNull();
fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
expect(screen.getByText("已完成的结果摘要")).toBeInTheDocument();
```

- [ ] **Step 2: Run the component test and verify it fails because the new labels/disclosure are absent**

Run: `pnpm test:run src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx`
Expected: FAIL with missing assistant labels and collapsed result control.

- [ ] **Step 3: Implement the smallest display-only change**

```tsx
{isTerminal(run) && run.summary_preview ? (
  <button aria-expanded={expandedResultIds.has(run.run_id)}>
    {expandedResultIds.has(run.run_id) ? "收起结果" : "查看结果"}
  </button>
) : null}
```

Keep API method names, event names, position, and stop behavior unchanged. Add focus-visible styles and flexible metadata wrapping.

- [ ] **Step 4: Re-run the component test**

Run: `pnpm test:run src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx`
Expected: PASS.

### Task 3: Confirm refresh after SubAgent SSE hints

**Files:**
- Modify: `console/src/pages/Chat/components/SubAgentRunMonitor/index.tsx`
- Test: `console/src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx`

- [ ] **Step 1: Write a failing fake-timer test**

```tsx
document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);
await vi.advanceTimersByTimeAsync(400);
expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(3);
```

- [ ] **Step 2: Run the test and verify it fails because only the immediate refresh occurs**

Run: `pnpm test:run src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx`
Expected: FAIL with two calls rather than three.

- [ ] **Step 3: Add a deduplicated confirmation timer**

```tsx
const confirmRefreshTimerRef = useRef<number | null>(null);

function refreshAfterSubAgentEvent() {
  void refresh();
  window.clearTimeout(confirmRefreshTimerRef.current ?? undefined);
  confirmRefreshTimerRef.current = window.setTimeout(() => void refresh(), 400);
}
```

Clear the timer on unmount and when the chat changes; retain the existing 10-second active-run polling.

- [ ] **Step 4: Re-run component tests**

Run: `pnpm test:run src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx`
Expected: PASS.

### Task 4: Document terminology and verify the complete change

**Files:**
- Modify: `CONTEXT.md`
- Test: `tests/unit/subagents/test_monitor_api.py`
- Test: `console/src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx`

- [ ] **Step 1: Record the display-term and budget-observation definitions**

```md
**助手**:
The chat-facing display term for one **Background SubAgent Run**.
```

- [ ] **Step 2: Run focused checks**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_monitor_api.py -q`
Expected: PASS.

Run: `pnpm test:run src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx`
Expected: PASS.

- [ ] **Step 3: Run changed-file hooks and review the diff**

Run: `venv/bin/python -m pre_commit run --files src/swe/app/subagents/models.py src/swe/app/subagents/run_store.py src/swe/app/subagents/runtime.py src/swe/app/subagents/monitor.py tests/unit/subagents/test_monitor_api.py`
Expected: PASS.

- [ ] **Step 4: Commit the verified implementation**

```bash
git add CONTEXT.md docs/superpowers/plans/2026-08-12-subagent-monitor-assistant-progress.md src/swe/app/subagents/models.py src/swe/app/subagents/run_store.py src/swe/app/subagents/runtime.py src/swe/app/subagents/monitor.py tests/unit/subagents/test_monitor_api.py console/src/api/types/chat.ts console/src/pages/Chat/components/SubAgentRunMonitor
git commit -m "feat(console): improve assistant run monitor"
```
