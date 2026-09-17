# Plan Review Card Protocol and Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `open_questions` and `confidence` from the Proposed Plan protocol and restyle the plan review card to match the clarification card without changing review decision behavior.

**Architecture:** Make the backend model the source of the new protocol, then update tool emission, accepted-plan context, console decision recording, and frontend metadata parsing to match. Keep the frontend review card in the normal message-rendering path and replace only its generic card wrapper/style with plan-card-specific markup and CSS. Follow TDD with focused backend and frontend tests before each implementation slice.

**Tech Stack:** Python 3, Pydantic, pytest, React 18, TypeScript, Less CSS Modules, Vitest, Testing Library.

---

### Task 1: Backend Proposed Plan Protocol

**Files:**
- Modify: `tests/unit/app/plans/test_models.py`
- Modify: `tests/unit/app/plans/test_store.py`
- Modify: `tests/unit/agents/tools/test_planning.py`
- Modify: `src/swe/app/plans/models.py`
- Modify: `src/swe/agents/tools/planning.py`

- [ ] **Step 1: Write failing model tests**

Update `_plan_payload()` in `tests/unit/app/plans/test_models.py` so it no
longer returns `open_questions` or `confidence`:

```python
def _plan_payload() -> dict:
    return {
        "title": "Investigate failing tests",
        "summary": "Find the smallest failing backend scope.",
        "steps": ["Inspect logs", "Add regression test"],
        "risks": ["May need frontend follow-up"],
        "verification": ["Run targeted pytest"],
    }
```

Update `test_proposed_plan_requires_review_fields()` so only retained fields are
required:

```python
@pytest.mark.parametrize(
    "missing_field",
    [
        "title",
        "summary",
        "steps",
        "risks",
        "verification",
    ],
)
def test_proposed_plan_requires_review_fields(missing_field: str) -> None:
    payload = _plan_payload()
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        ProposedPlanCreate.model_validate(payload)
```

Add a strict old-field rejection test:

```python
@pytest.mark.parametrize("removed_field", ["open_questions", "confidence"])
def test_proposed_plan_rejects_removed_review_fields(
    removed_field: str,
) -> None:
    payload = _plan_payload()
    payload[removed_field] = [] if removed_field == "open_questions" else 0.8

    with pytest.raises(ValidationError):
        ProposedPlanCreate.model_validate(payload)
```

- [ ] **Step 2: Verify model tests fail for the right reason**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/app/plans/test_models.py -q
```

Expected: failure because `open_questions` and `confidence` are still required
or accepted by `ProposedPlanCreate`.

- [ ] **Step 3: Write failing store/tool tests**

Update `_payload()` in `tests/unit/app/plans/test_store.py`:

```python
def _payload(title: str = "Plan title") -> ProposedPlanCreate:
    return ProposedPlanCreate(
        title=title,
        summary="Plan summary",
        steps=["Read code", "Write tests"],
        risks=["Unknown edge case"],
        verification=["Run pytest"],
    )
```

Update `test_submit_proposed_plan_persists_before_review_card()` in
`tests/unit/agents/tools/test_planning.py` so the tool call omits the removed
arguments and asserts the card does not emit them:

```python
response = await tool(
    title="Fix failing test",
    summary="Narrow the failing scope and patch it.",
    steps=["Reproduce", "Patch", "Verify"],
    risks=["Hidden regression"],
    verification=["Run pytest"],
)

card = response.metadata["plan_interaction_card"]
assert card["card_type"] == "plan_review"
assert card["plan_id"].startswith("plan-")
assert card["title"] == "Fix failing test"
assert "open_questions" not in card
assert "confidence" not in card
```

Replace `test_submit_proposed_plan_allows_empty_open_questions()` with:

```python
@pytest.mark.asyncio
async def test_submit_proposed_plan_rejects_removed_fields(
    tmp_path: Path,
) -> None:
    tool = create_submit_proposed_plan_tool(
        request_context={
            "chat_id": "chat-2",
            "session_id": "session-2",
            "turn_id": "turn-2",
            "user_id": "user-2",
        },
        workspace_dir=tmp_path,
    )

    with pytest.raises(TypeError):
        await tool(
            title="B2B 企业服务客户经营计划（6个月）",
            summary="将客户经营计划整理为可执行的半年路线图。",
            steps=["保存计划文档", "生成分享版本"],
            risks=["客户成功团队人手不足"],
            verification=["确认 plan 文件已保存"],
            open_questions=[],
            confidence=0.9,
        )
```

- [ ] **Step 4: Verify store/tool tests fail for the right reason**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/app/plans/test_store.py tests/unit/agents/tools/test_planning.py -q
```

Expected: failure because the production model and tool still require the
removed fields.

- [ ] **Step 5: Implement backend protocol removal**

In `src/swe/app/plans/models.py`, remove `open_questions`,
`confidence`, and the `_open_questions_items_must_be_non_empty()` validator from
`ProposedPlanCreate`. Remove the same fields from `PlanReviewCard` and from
`PlanReviewCard.from_plan()`:

```python
class ProposedPlanCreate(_StrictPlanModel):
    """创建 Proposed Plan 时由模型产出的业务内容。"""

    title: str
    summary: str
    steps: list[str]
    risks: list[str]
    verification: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class PlanReviewCard(PlanInteractionCard):
    """展示 Proposed Plan 并收集审核动作的卡片。"""

    card_type: Literal["plan_review"] = "plan_review"
    plan_id: str
    title: str
    summary: str
    steps: list[str]
    risks: list[str]
    verification: list[str]
    submitted_decision: PlanReviewDecisionType | None = None
```

```python
return cls(
    plan_id=plan.plan_id,
    title=plan.title,
    summary=plan.summary,
    steps=plan.steps,
    risks=plan.risks,
    verification=plan.verification,
)
```

In `src/swe/agents/tools/planning.py`, remove `open_questions` and `confidence`
from `submit_proposed_plan()` and the `ProposedPlanCreate()` call. Update the
docstring:

```python
async def submit_proposed_plan(
    title: str,
    summary: str,
    steps: list[str],
    risks: list[str],
    verification: list[str],
) -> ToolResponse:
    """在没有未决问题时持久化 Proposed Plan，并返回计划审核卡片元数据。"""
```

- [ ] **Step 6: Verify backend protocol tests pass**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/app/plans/test_models.py tests/unit/app/plans/test_store.py tests/unit/agents/tools/test_planning.py -q
```

Expected: all selected tests pass.

### Task 2: Accepted Plan and Console Decision Context

**Files:**
- Modify: `tests/unit/routers/test_console_chat_stream.py`
- Modify: `tests/unit/app/test_task_progress_switch.py`
- Modify: `src/swe/app/routers/console.py`
- Modify: `src/swe/agents/react_agent.py`

- [ ] **Step 1: Write failing accepted-context tests**

In `tests/unit/routers/test_console_chat_stream.py`, update all
`ProposedPlanCreate(...)` calls in plan-review tests to omit
`open_questions` and `confidence`. In execute-path assertions, verify the
accepted plan context excludes the removed keys:

```python
accepted_plan = tracker.requests[-1].meta["accepted_plan"]
assert accepted_plan["plan_id"] == plan.plan_id
assert accepted_plan["steps"] == ["Inspect"]
assert "open_questions" not in accepted_plan
assert "confidence" not in accepted_plan
```

In `tests/unit/app/test_task_progress_switch.py`, remove `open_questions` and
`confidence` from plan-review test fixtures that are only constructing the new
card contract.

- [ ] **Step 2: Verify accepted-context tests fail for the right reason**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py tests/unit/app/test_task_progress_switch.py -q
```

Expected: failure because `_accepted_plan_context()` and some fixtures still use
the removed fields.

- [ ] **Step 3: Implement context cleanup**

In `src/swe/app/routers/console.py`, update `_accepted_plan_context()`:

```python
def _accepted_plan_context(plan: Any) -> dict[str, Any]:
    """构造传给执行轮次的只读计划上下文。"""
    return {
        "plan_id": plan.plan_id,
        "title": plan.title,
        "summary": plan.summary,
        "steps": list(plan.steps),
        "risks": list(plan.risks),
        "verification": list(plan.verification),
    }
```

In `src/swe/agents/react_agent.py`, remove `open_questions` from the accepted
plan item loop:

```python
for field in ("steps", "risks", "verification"):
    items = _format_accepted_plan_items(accepted_plan.get(field))
    if not items:
        continue
    lines.append(f"- {field}:")
    lines.extend(
        f"  {index}. {item}" for index, item in enumerate(items, 1)
    )
```

- [ ] **Step 4: Verify accepted-context tests pass**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py tests/unit/app/test_task_progress_switch.py -q
```

Expected: all selected tests pass.

### Task 3: Frontend Card Contract

**Files:**
- Modify: `console/src/pages/Chat/messageMeta.test.ts`
- Modify: `console/src/pages/Chat/messageMeta.ts`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Write failing metadata tests**

In `console/src/pages/Chat/messageMeta.test.ts`, remove `open_questions` and
`confidence` from the valid `plan_review` fixture:

```typescript
plan_interaction_card: {
  card_type: "plan_review",
  plan_id: "plan-123",
  title: "Fix bug",
  summary: "Patch safely",
  steps: ["Read"],
  risks: [],
  verification: ["Test"],
},
```

Add a rejection case for the old protocol fields:

```typescript
expect(
  extractPlanInteractionCard({
    metadata: {
      plan_interaction_card: {
        card_type: "plan_review",
        plan_id: "old-plan",
        title: "Old",
        summary: "Old shape",
        steps: ["Read"],
        risks: [],
        verification: ["Test"],
        open_questions: [],
        confidence: 0.8,
      },
    },
  }),
).toBeNull();
```

In `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`, remove the
removed fields from all `PlanReviewCard` test data.

- [ ] **Step 2: Verify frontend metadata tests fail**

Run:

```bash
cd console && pnpm test:run -- messageMeta PlanInteractionCards
```

Expected: failure because `ChatPlanReviewCardData` and
`normalizePlanInteractionCard()` still require `open_questions` and
`confidence`.

- [ ] **Step 3: Implement frontend contract removal**

In `console/src/pages/Chat/messageMeta.ts`, remove the fields from
`ChatPlanReviewCardData`:

```typescript
export interface ChatPlanReviewCardData {
  card_type: "plan_review";
  plan_id: string;
  title: string;
  summary: string;
  steps: string[];
  risks: string[];
  verification: string[];
  status?: "pending" | "submitted";
}
```

Update the `plan_review` branch of `normalizePlanInteractionCard()` so it
requires retained fields and rejects old fields:

```typescript
if (
  typeof card.plan_id !== "string" ||
  typeof card.title !== "string" ||
  typeof card.summary !== "string" ||
  !isStringArray(card.steps) ||
  !isStringArray(card.risks) ||
  !isStringArray(card.verification) ||
  "open_questions" in card ||
  "confidence" in card
) {
  return null;
}
```

Return only retained fields.

- [ ] **Step 4: Verify frontend contract tests pass**

Run:

```bash
cd console && pnpm test:run -- messageMeta PlanInteractionCards
```

Expected: selected frontend tests pass.

### Task 4: Plan Review Card Style

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less`

- [ ] **Step 1: Write failing style/structure tests**

Update the `OperateCard` test mock in
`console/src/pages/Chat/components/PlanInteractionCards.test.tsx` to make
generic-card fallback visible:

```typescript
OperateCard: Object.assign(
  ({
    header,
    body,
  }: {
    header: { title: string };
    body: { children: React.ReactNode };
  }) => (
    <section data-testid="generic-operate-card">
      <h3>{header.title}</h3>
      {body.children}
    </section>
  ),
  {
    LineBody: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
  },
),
```

In the review-card tests, assert that the custom card structure is used:

```typescript
expect(screen.queryByTestId("generic-operate-card")).not.toBeInTheDocument();
expect(screen.getByRole("region", { name: "Fix bug" })).toHaveAttribute(
  "data-plan-review-card",
  "true",
);
expect(screen.getByText("Steps")).toBeInTheDocument();
expect(screen.getByText("Risks")).toBeInTheDocument();
expect(screen.getByText("Verification")).toBeInTheDocument();
expect(screen.queryByText("Open questions")).not.toBeInTheDocument();
expect(screen.queryByText(/Confidence:/)).not.toBeInTheDocument();
```

- [ ] **Step 2: Verify style/structure tests fail**

Run:

```bash
cd console && pnpm test:run -- PlanInteractionCards
```

Expected: failure because `PlanReviewCard` still uses `OperateCard` and renders
old sections.

- [ ] **Step 3: Implement review-card markup**

In `console/src/pages/Chat/components/PlanInteractionCards.tsx`, remove unused
AntD imports after replacing the review card. Keep only imports still used by
clarification cards. Replace `PlanList` with a CSS-module based section:

```tsx
function PlanList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className={styles.reviewSection}>
      <h4>{title}</h4>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
```

Replace the `PlanReviewCard` return value with:

```tsx
return (
  <section
    className={styles.planReviewCard}
    data-plan-review-card="true"
    role="region"
    aria-label={data.title}
  >
    <header className={styles.reviewHeader}>
      <div className={styles.reviewHeading}>
        <ClipboardCheck aria-hidden="true" size={16} />
        <div>
          <strong>{data.title}</strong>
          <p>{data.summary}</p>
        </div>
      </div>
    </header>

    <div className={styles.reviewContent}>
      <PlanList title="Steps" items={data.steps} />
      <PlanList title="Risks" items={data.risks} />
      <PlanList title="Verification" items={data.verification} />
      <textarea
        className={styles.reviewFeedback}
        placeholder="Feedback"
        value={feedback}
        disabled={submitted}
        onChange={(event) => setFeedback(event.target.value)}
      />
    </div>

    <footer className={styles.reviewActions}>
      <button
        type="button"
        className={styles.reviewSecondaryButton}
        disabled={submitted}
        onClick={() => handleDecision("revise")}
      >
        Continue modifying
      </button>
      <button
        type="button"
        className={styles.reviewSecondaryButton}
        disabled={submitted}
        onClick={() => handleDecision("exit_plan")}
      >
        Exit Plan Mode
      </button>
      <button
        type="button"
        className={styles.reviewPrimaryButton}
        disabled={submitted}
        onClick={() => handleDecision("execute")}
      >
        Execute
      </button>
    </footer>
  </section>
);
```

- [ ] **Step 4: Implement review-card styles**

In `console/src/pages/Chat/components/PlanInteractionCards.module.less`, add
shared variables to `.planReviewCard` by mirroring the clarification palette.
Keep class names separate so the review card can evolve independently:

```less
.planReviewCard {
  --clarification-card-bg: #f3f4eb;
  --clarification-border: rgba(225, 222, 214, 0.9);
  --clarification-active-bg: #e6e7de;
  --clarification-text: #56584f;
  --clarification-muted: #a3a49a;
  --clarification-accent: #4f6f63;
  --clarification-accent-hover: #45675b;
  --clarification-accent-text: #edf2ed;

  width: min(100%, 818px);
  margin: 0 auto;
  padding: 13px 8px 8px;
  overflow: hidden;
  border: 1px solid var(--clarification-border);
  border-radius: 17px;
  background: var(--clarification-card-bg);
  box-shadow:
    0 1px 2px rgba(78, 75, 65, 0.06),
    0 2px 10px rgba(78, 75, 65, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.46);
  color: var(--clarification-text);
  animation: clarification-enter 160ms ease-out both;
}
```

Add dark-mode overrides matching `.planClarificationCard`. Add
`.reviewHeader`, `.reviewHeading`, `.reviewContent`, `.reviewSection`,
`.reviewFeedback`, `.reviewActions`, `.reviewSecondaryButton`, and
`.reviewPrimaryButton` using the same spacing, focus, hover, and disabled
patterns as `.cardHeader`, `.textArea`, `.dismissButton`, and
`.continueButton`.

- [ ] **Step 5: Verify frontend style tests pass**

Run:

```bash
cd console && pnpm test:run -- PlanInteractionCards
```

Expected: selected tests pass.

### Task 5: Full Focused Verification

**Files:**
- Modify: no production files unless verification exposes a defect.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
../../venv/bin/python -m pytest tests/unit/app/plans/test_models.py tests/unit/app/plans/test_store.py tests/unit/agents/tools/test_planning.py tests/unit/routers/test_console_chat_stream.py tests/unit/app/test_task_progress_switch.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd console && pnpm test:run -- messageMeta PlanInteractionCards
```

Expected: all selected frontend tests pass. Existing jsdom `getComputedStyle`
pseudo-element messages are acceptable if tests pass.

- [ ] **Step 3: Run frontend type check**

Run:

```bash
cd console && pnpm build
```

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 4: Run GitNexus change detection**

Run GitNexus on all worktree changes:

```text
detect_changes(scope="all", repo="CoPaw", worktree="/Users/shixiangyi/code/Swe/.worktrees/plan-review-card-protocol-style")
```

Expected: changed symbols match plan protocol, console context, and plan card UI.

- [ ] **Step 5: Commit implementation**

Stage only files changed by this implementation and commit:

```bash
git add src/swe/app/plans/models.py src/swe/agents/tools/planning.py src/swe/app/routers/console.py src/swe/agents/react_agent.py tests/unit/app/plans/test_models.py tests/unit/app/plans/test_store.py tests/unit/agents/tools/test_planning.py tests/unit/routers/test_console_chat_stream.py tests/unit/app/test_task_progress_switch.py console/src/pages/Chat/messageMeta.ts console/src/pages/Chat/messageMeta.test.ts console/src/pages/Chat/components/PlanInteractionCards.tsx console/src/pages/Chat/components/PlanInteractionCards.module.less console/src/pages/Chat/components/PlanInteractionCards.test.tsx docs/superpowers/plans/2026-06-14-plan-review-card-protocol-and-style.md
git commit -m "feat(planning): simplify plan review protocol"
```
