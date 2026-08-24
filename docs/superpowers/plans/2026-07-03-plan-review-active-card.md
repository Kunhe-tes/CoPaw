# Plan Review Active Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `submit_proposed_plan` render as a single active review card like `ask_plan_clarification`, while preserving read-only historical snapshots and fixing Plan Mode decision behavior.

**Architecture:** Keep backend plan decision semantics intact and fix the Console presentation layer. Historical `plan_review` cards become read-only snapshots inside chat history; a new active review card renders near the composer for the latest unhandled Proposed Plan. Plan decision side effects are coordinated through existing chat submit metadata and local Plan Mode state.

**Tech Stack:** React, TypeScript, CSS modules, Vitest/Testing Library, existing Console chat event emitter, existing FastAPI plan decision stream.

---

## File Structure

- Modify `console/src/pages/Chat/messageMeta.ts`
  - Extend `ChatPlanReviewCardData` with review decision status fields needed by snapshots.
  - Normalize backend card metadata without changing the backend protocol.

- Modify `console/src/pages/Chat/sessionApi/index.ts`
  - Collect submitted Plan Review decisions, not just plan IDs.
  - Mark historical cards as submitted with `submitted_decision` and `feedback`.

- Modify `console/src/pages/Chat/components/PlanInteractionCards.tsx`
  - Add active review-card discovery similar to `findLatestPlanClarificationCard`.
  - Split active `PlanReviewCard` from read-only `PlanReviewSnapshot`.
  - Change `Continue modifying` to prepare the next user input as revision content instead of submitting immediately.

- Modify `console/src/pages/Chat/components/PlanInteractionCards.module.less`
  - Add snapshot status styles.
  - Move summary into a wrapping body block.
  - Add Plan Mode exit feedback animation hooks if needed by `planMode.tsx`.

- Modify `console/src/pages/Chat/planMode.tsx`
  - Allow the active Plan Mode control to animate out when disabled.

- Modify `console/src/pages/Chat/index.tsx`
  - Render `ActivePlanReviewCard` beside `ActivePlanClarificationCard`.
  - Track pending Plan Revision Input for the current session.
  - Attach `plan_interaction_response.decision=revise` to the next submitted user message after `Continue modifying`.
  - Close local Plan Mode state for `execute` and `exit_plan` decisions.

- Modify tests:
  - `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
  - `console/src/pages/Chat/sessionApi/index.test.ts`
  - `console/src/pages/Chat/planMode.test.tsx`
  - `console/src/pages/Chat/index.test.tsx`
  - `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.test.tsx` only if SSE short-circuit handling is changed in the request hook.

Before editing any function or component, run GitNexus impact analysis for the target symbol. Known pre-analysis result: `processSSEResponse` has LOW risk with 2 direct callers; TSX component symbols were not indexed, so use local tests as the primary guard for UI changes.

---

### Task 1: Preserve Plan Review Decision Metadata In Session Conversion

**Files:**
- Modify: `console/src/pages/Chat/messageMeta.ts`
- Modify: `console/src/pages/Chat/sessionApi/index.ts`
- Test: `console/src/pages/Chat/sessionApi/index.test.ts`

- [ ] **Step 1: Run impact analysis**

Run:

```bash
npx gitnexus analyze
```

Only run this if a GitNexus tool reports the index is stale.

Then run GitNexus impact for the edited symbols:

```text
mcp__gitnexus.impact({
  repo: "CoPaw",
  target: "extractSubmittedPlanReviewId",
  file_path: "console/src/pages/Chat/sessionApi/index.ts",
  kind: "Function",
  direction: "upstream",
  summaryOnly: true
})
```

Expected: risk is not HIGH or CRITICAL. If HIGH or CRITICAL, stop and report the blast radius before editing.

- [ ] **Step 2: Write failing tests for decision-aware snapshots**

Add tests in `console/src/pages/Chat/sessionApi/index.test.ts` that build messages containing a Proposed Plan assistant message and a later user message with `plan_interaction_response`.

Test cases:

```tsx
it("marks a restored plan review card as accepted after execute", () => {
  const converted = convertMessages([
    {
      id: "assistant-plan",
      role: "assistant",
      content: "",
      metadata: {
        plan_interaction_card: {
          card_type: "plan_review",
          plan_id: "plan-1",
          title: "Fix bug",
          summary: "Investigate and patch",
          steps: ["Read code"],
          risks: ["Regression"],
          verification: ["Focused tests"],
        },
      },
    },
    {
      id: "user-execute",
      role: "user",
      content: "Execute plan plan-1",
      metadata: {
        plan_interaction_response: {
          card_type: "plan_review",
          plan_id: "plan-1",
          decision: "execute",
        },
      },
    },
  ] as never);

  const planCard = converted[0].cards?.find(
    (card) => card.code === "PlanInteraction",
  );

  expect(planCard?.data).toMatchObject({
    card_type: "plan_review",
    plan_id: "plan-1",
    status: "submitted",
    submitted_decision: "execute",
  });
});

it("marks a restored plan review card as revision requested with feedback", () => {
  const converted = convertMessages([
    {
      id: "assistant-plan",
      role: "assistant",
      content: "",
      metadata: {
        plan_interaction_card: {
          card_type: "plan_review",
          plan_id: "plan-2",
          title: "Refactor",
          summary: "Split UI state",
          steps: ["Read code"],
          risks: [],
          verification: [],
        },
      },
    },
    {
      id: "user-revise",
      role: "user",
      content: "Keep Plan Mode and narrow the scope",
      metadata: {
        plan_interaction_response: {
          card_type: "plan_review",
          plan_id: "plan-2",
          decision: "revise",
          feedback: "Keep Plan Mode and narrow the scope",
        },
      },
    },
  ] as never);

  const planCard = converted[0].cards?.find(
    (card) => card.code === "PlanInteraction",
  );

  expect(planCard?.data).toMatchObject({
    card_type: "plan_review",
    plan_id: "plan-2",
    status: "submitted",
    submitted_decision: "revise",
    feedback: "Keep Plan Mode and narrow the scope",
  });
});
```

- [ ] **Step 3: Run the tests and verify failure**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/sessionApi/index.test.ts
```

Expected: tests fail because `submitted_decision` and `feedback` are not preserved.

- [ ] **Step 4: Extend plan review card types**

In `console/src/pages/Chat/messageMeta.ts`, update `ChatPlanReviewCardData`:

```ts
export type PlanReviewDecision = "revise" | "execute" | "exit_plan";

export interface ChatPlanReviewCardData {
  card_type: "plan_review";
  plan_id: string;
  title: string;
  summary: string;
  steps: string[];
  risks: string[];
  verification: string[];
  status?: "pending" | "submitted";
  submitted_decision?: PlanReviewDecision;
  feedback?: string;
}
```

Update `normalizePlanInteractionCard` to preserve only trusted normalized fields:

```ts
return {
  card_type: "plan_review",
  plan_id: card.plan_id,
  title: card.title,
  summary: card.summary,
  steps: card.steps,
  risks: card.risks,
  verification: card.verification,
  status: card.status === "submitted" ? "submitted" : undefined,
  submitted_decision:
    card.submitted_decision === "revise" ||
    card.submitted_decision === "execute" ||
    card.submitted_decision === "exit_plan"
      ? card.submitted_decision
      : undefined,
  feedback: typeof card.feedback === "string" ? card.feedback : undefined,
};
```

- [ ] **Step 5: Replace ID-only collection with decision collection**

In `console/src/pages/Chat/sessionApi/index.ts`, replace the ID-only helper with a metadata helper:

```ts
type SubmittedPlanReview = {
  planId: string;
  decision: "revise" | "execute" | "exit_plan";
  feedback?: string;
};

function extractSubmittedPlanReview(message: Message): SubmittedPlanReview | null {
  const record = asRecord(message);
  const metadata = asRecord(record?.metadata);
  const meta = asRecord(record?.meta);
  const bizParams = asRecord(record?.biz_params);
  const candidates = [
    record?.plan_interaction_response,
    metadata?.plan_interaction_response,
    meta?.plan_interaction_response,
    bizParams?.plan_interaction_response,
  ];

  for (const candidate of candidates) {
    const response = asRecord(candidate);
    if (!response) continue;
    const planId = response.plan_id;
    const decision = response.decision;
    if (
      typeof planId === "string" &&
      planId &&
      (decision === "revise" ||
        decision === "execute" ||
        decision === "exit_plan")
    ) {
      return {
        planId,
        decision,
        feedback:
          typeof response.feedback === "string" ? response.feedback : undefined,
      };
    }
  }

  return null;
}

function collectSubmittedPlanReviews(
  messages: Message[],
): Map<string, SubmittedPlanReview> {
  return new Map(
    messages
      .map(extractSubmittedPlanReview)
      .filter((item): item is SubmittedPlanReview => Boolean(item))
      .map((item) => [item.planId, item]),
  );
}
```

Update `markSubmittedPlanReviewCard`:

```ts
function markSubmittedPlanReviewCard(
  card: ChatPlanInteractionCardData | null,
  submittedPlanReviews: Map<string, SubmittedPlanReview>,
): ChatPlanInteractionCardData | null {
  if (!card || card.card_type !== "plan_review") {
    return card;
  }

  const submitted = submittedPlanReviews.get(card.plan_id);
  if (!submitted) {
    return card;
  }

  return {
    ...card,
    status: "submitted",
    submitted_decision: submitted.decision,
    feedback: submitted.feedback,
  } satisfies ChatPlanReviewCardData;
}
```

Update call sites to pass `submittedPlanReviews`.

- [ ] **Step 6: Run tests**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/sessionApi/index.test.ts
```

Expected: PASS.

---

### Task 2: Split Active Plan Review From Historical Snapshot

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Run impact analysis**

Run GitNexus impact for candidate component symbols. If GitNexus cannot resolve TSX components, record the result and proceed with local tests:

```text
mcp__gitnexus.impact({
  repo: "CoPaw",
  target: "PlanReviewCard",
  file_path: "console/src/pages/Chat/components/PlanInteractionCards.tsx",
  kind: "Function",
  direction: "upstream",
  summaryOnly: true
})
```

- [ ] **Step 2: Write failing tests for active review behavior**

Add tests in `PlanInteractionCards.test.tsx`:

```tsx
it("renders only the latest unhandled plan review as active", () => {
  renderActivePlanReview([
    createPlanReviewMessage({
      messageId: "message-1",
      planId: "plan-1",
      title: "Old plan",
    }),
    createPlanReviewMessage({
      messageId: "message-2",
      planId: "plan-2",
      title: "Latest plan",
    }),
  ]);

  expect(screen.queryByText("Old plan")).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Latest plan" })).toHaveAttribute(
    "data-active-plan-review-card",
    "true",
  );
});

it("does not render an active plan review after a later user message", () => {
  renderActivePlanReview([
    createPlanReviewMessage({
      messageId: "message-1",
      planId: "plan-1",
      title: "Needs review",
    }),
    {
      id: "user-later",
      role: "user",
      cards: [
        {
          code: "AgentScopeRuntimeRequestCard",
          data: {
            input: [
              {
                role: "user",
                type: "message",
                content: [{ type: "text", text: "I have more context" }],
              },
            ],
          },
        },
      ],
    },
  ]);

  expect(screen.queryByText("Needs review")).not.toBeInTheDocument();
});

it("renders historical plan review as a read-only snapshot", () => {
  render(
    <PlanReviewSnapshot
      data={{
        card_type: "plan_review",
        plan_id: "plan-1",
        title: "Accepted plan",
        summary: "Long summary",
        steps: [],
        risks: [],
        verification: [],
        status: "submitted",
        submitted_decision: "execute",
      }}
    />,
  );

  expect(screen.getByText("已接受并开始执行")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Execute" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Continue modifying" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Exit Plan Mode" })).not.toBeInTheDocument();
});
```

Add helper functions in the test file:

```tsx
function createPlanReviewMessage({
  messageId,
  planId,
  title,
}: {
  messageId: string;
  planId: string;
  title: string;
}): IAgentScopeRuntimeWebUIMessage {
  return {
    id: messageId,
    role: "assistant",
    cards: [
      {
        code: "PlanInteraction",
        data: {
          card_type: "plan_review",
          plan_id: planId,
          title,
          summary: "Review this plan",
          steps: ["Step 1"],
          risks: [],
          verification: [],
        },
      },
    ],
  };
}

function renderActivePlanReview(messages: IAgentScopeRuntimeWebUIMessage[]) {
  return render(
    <ChatAnywhereMessagesContext.Provider value={{ messages } as never}>
      <ActivePlanReviewCard />
    </ChatAnywhereMessagesContext.Provider>,
  );
}
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: FAIL because `ActivePlanReviewCard` and `PlanReviewSnapshot` do not exist yet.

- [ ] **Step 4: Add active plan review discovery**

In `PlanInteractionCards.tsx`, add:

```ts
function isPlanReviewCardData(data: unknown): data is ChatPlanReviewCardData {
  return (
    Boolean(data) &&
    typeof data === "object" &&
    (data as { card_type?: unknown }).card_type === "plan_review"
  );
}

function findLatestPlanReviewCard(
  messages: IAgentScopeRuntimeWebUIMessage[],
): {
  data: ChatPlanReviewCardData;
  instanceKey: string;
} | null {
  let hasLaterUserMessage = false;

  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const message = messages[messageIndex];
    if (message?.role === "user") {
      hasLaterUserMessage = true;
      continue;
    }

    const cards = message?.cards || [];
    for (let cardIndex = cards.length - 1; cardIndex >= 0; cardIndex -= 1) {
      const card = cards[cardIndex];
      if (
        !hasLaterUserMessage &&
        card.code === PLAN_INTERACTION_CARD_CODE &&
        isPlanReviewCardData(card.data) &&
        card.data.status !== "submitted"
      ) {
        return {
          data: card.data,
          instanceKey: `${message.id}:${card.id || card.code}:${cardIndex}`,
        };
      }
    }
  }

  return null;
}

export function ActivePlanReviewCard({
  onContinueModifying,
  onPlanModeDecision,
}: {
  onContinueModifying?: (data: ChatPlanReviewCardData) => void;
  onPlanModeDecision?: (enabled: boolean) => void;
}) {
  const review = useContextSelector(ChatAnywhereMessagesContext, (value) =>
    findLatestPlanReviewCard(value.messages || []),
  );

  if (!review) {
    return null;
  }

  return (
    <PlanReviewCard
      data={review.data}
      active
      cardInstanceKey={review.instanceKey}
      onContinueModifying={onContinueModifying}
      onPlanModeDecision={onPlanModeDecision}
    />
  );
}
```

- [ ] **Step 5: Split snapshot rendering from active rendering**

Update `PlanReviewCard` props:

```ts
export function PlanReviewCard({
  data,
  active = false,
  onContinueModifying,
  onPlanModeDecision,
}: {
  data: ChatPlanReviewCardData;
  active?: boolean;
  cardInstanceKey?: string;
  onContinueModifying?: (data: ChatPlanReviewCardData) => void;
  onPlanModeDecision?: (enabled: boolean) => void;
}) {
  if (!active) {
    return <PlanReviewSnapshot data={data} />;
  }

  return (
    <PlanReviewActiveCard
      data={data}
      onContinueModifying={onContinueModifying}
      onPlanModeDecision={onPlanModeDecision}
    />
  );
}
```

Add `PlanReviewSnapshot`:

```tsx
export function PlanReviewSnapshot({ data }: { data: ChatPlanReviewCardData }) {
  const statusLabel =
    data.submitted_decision === "execute"
      ? "已接受并开始执行"
      : data.submitted_decision === "revise"
      ? "已要求修改"
      : data.submitted_decision === "exit_plan"
      ? "已退出计划模式"
      : "计划待确认";

  return (
    <section
      className={styles.planReviewCard}
      data-plan-review-snapshot="true"
      role="region"
      aria-label={data.title}
    >
      <header className={styles.reviewHeader}>
        <div className={styles.reviewHeading}>
          <div>
            <strong>{data.title}</strong>
            <span className={styles.reviewStatus}>{statusLabel}</span>
          </div>
        </div>
      </header>
      <div className={styles.reviewContent}>
        {data.summary ? (
          <p className={styles.reviewSummary}>{data.summary}</p>
        ) : null}
        {data.feedback ? (
          <section className={styles.reviewSection}>
            <h4>修改意见</h4>
            <p className={styles.reviewFeedbackSummary}>{data.feedback}</p>
          </section>
        ) : null}
        <PlanList title="执行步骤" items={data.steps} />
        <PlanList title="风险提示" items={data.risks} />
        <PlanList title="验证方式" items={data.verification} />
      </div>
    </section>
  );
}
```

Rename the old active implementation to `PlanReviewActiveCard`.

- [ ] **Step 6: Change active card content and actions**

In `PlanReviewActiveCard`, remove header icon and render wrapping summary:

```tsx
<header className={styles.reviewHeader}>
  <div className={styles.reviewHeading}>
    <div>
      <strong>{data.title}</strong>
    </div>
  </div>
</header>

<div className={styles.reviewContent}>
  {data.summary ? <p className={styles.reviewSummary}>{data.summary}</p> : null}
  <PlanList title="执行步骤" items={data.steps} />
  <PlanList title="风险提示" items={data.risks} />
  <PlanList title="验证方式" items={data.verification} />
</div>
```

For `Continue modifying`, call the callback and do not emit a submit event:

```tsx
<button
  type="button"
  className={styles.reviewSecondaryButton}
  disabled={submitted}
  onClick={() => onContinueModifying?.(data)}
>
  Continue modifying
</button>
```

For `execute` and `exit_plan`, keep submit event behavior and call `onPlanModeDecision(false)` only after submit is initiated:

```ts
const handleDecision = (decision: "execute" | "exit_plan") => {
  if (submitted) return;

  const mode = "normal";
  const query =
    decision === "execute" ? `Execute plan ${data.plan_id}` : "Exit Plan Mode";

  setSubmitted(true);
  onPlanModeDecision?.(false);
  emit({
    type: "handleSubmit",
    data: {
      query,
      fileList: [],
      biz_params: {
        mode,
        plan_interaction_response: {
          card_type: "plan_review",
          plan_id: data.plan_id,
          decision,
        },
      },
    },
  });
};
```

- [ ] **Step 7: Add summary wrapping styles**

In `PlanInteractionCards.module.less`, replace header summary truncation with body summary:

```less
.reviewSummary {
  margin: 0;
  border-radius: 10px;
  background: rgba(230, 231, 222, 0.58);
  padding: 10px 12px;
  color: var(--clarification-text);
  font-size: 13px;
  line-height: 20px;
  overflow-wrap: anywhere;
  white-space: normal;
  word-break: break-word;
}

.reviewStatus {
  display: inline-flex;
  margin-top: 4px;
  border-radius: 999px;
  background: rgba(79, 111, 99, 0.1);
  color: var(--clarification-accent);
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  padding: 0 8px;
}

.reviewFeedbackSummary {
  margin: 0;
  color: var(--clarification-text);
  font-size: 13px;
  line-height: 20px;
  overflow-wrap: anywhere;
  white-space: normal;
}
```

Remove or stop using `.reviewIcon` and `.reviewHeading p`.

- [ ] **Step 8: Run tests**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: PASS.

---

### Task 3: Wire Plan Revision Input Through Chat Submission

**Files:**
- Modify: `console/src/pages/Chat/index.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Test: `console/src/pages/Chat/index.test.tsx`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Run impact analysis**

Run GitNexus impact for `preparePlanModeSubmit` before changing submit behavior:

```text
mcp__gitnexus.impact({
  repo: "CoPaw",
  target: "preparePlanModeSubmit",
  file_path: "console/src/pages/Chat/planMode.tsx",
  kind: "Function",
  direction: "upstream",
  summaryOnly: true
})
```

Also run impact for `customFetch` if GitNexus can resolve it from `console/src/pages/Chat/index.tsx`.

- [ ] **Step 2: Write failing tests for deferred revise**

In `PlanInteractionCards.test.tsx`, update the review decision test:

```tsx
it("does not submit immediately when continuing plan modification", async () => {
  const submit = captureSubmitEvents();
  const onContinueModifying = vi.fn();

  render(
    <PlanReviewCard
      active
      data={{
        card_type: "plan_review",
        plan_id: "plan-123",
        title: "Fix bug",
        summary: "Investigate and patch",
        steps: ["Read code"],
        risks: [],
        verification: [],
      }}
      onContinueModifying={onContinueModifying}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));

  expect(onContinueModifying).toHaveBeenCalledWith(
    expect.objectContaining({ plan_id: "plan-123" }),
  );
  expect(submit.handler).not.toHaveBeenCalled();

  submit.cleanup();
});
```

In `index.test.tsx`, add a test around the chat submit flow:

```tsx
it("submits the next user input as a plan revision after Continue modifying", async () => {
  renderChatWithPlanReview({
    plan_id: "plan-123",
    title: "Fix bug",
  });

  fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));
  await userEvent.type(
    screen.getByRole("textbox"),
    "Narrow the implementation scope",
  );
  fireEvent.click(screen.getByRole("button", { name: /send/i }));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/console/chat"),
      expect.objectContaining({
        body: expect.stringContaining('"decision":"revise"'),
      }),
    );
  });

  expect(fetchMock).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({
      body: expect.stringContaining('"feedback":"Narrow the implementation scope"'),
    }),
  );
});
```

Use the existing Chat test helpers for rendering and fetch mocks; if no `renderChatWithPlanReview` helper exists, create one locally in the test file by following nearby session setup patterns.

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx src/pages/Chat/index.test.tsx
```

Expected: FAIL because `Continue modifying` still submits immediately and no pending revision state exists.

- [ ] **Step 4: Add pending revision state**

In `index.tsx`, add state near Plan Mode state:

```ts
type PendingPlanRevision = {
  planId: string;
  title: string;
};

const [pendingPlanRevision, setPendingPlanRevision] =
  useState<PendingPlanRevision | null>(null);
```

Add handler:

```ts
const handleContinueModifyingPlan = useCallback(
  (data: ChatPlanReviewCardData) => {
    setPendingPlanRevision({
      planId: data.plan_id,
      title: data.title,
    });
    setPlanModeEnabled(true);
    document.dispatchEvent(
      new CustomEvent("runtime-input-focus", {
        detail: {
          placeholder: "请输入需要修改的内容",
        },
      }),
    );
  },
  [],
);
```

If the input component already exposes a focus event, use the existing event name instead of adding `runtime-input-focus`.

- [ ] **Step 5: Attach revise metadata in `handleBeforeSubmit`**

Update `handleBeforeSubmit` in `index.tsx`:

```ts
const handleBeforeSubmit: NonNullable<
  IAgentScopeRuntimeWebUISenderOptions["beforeSubmit"]
> = async (data) => {
  if (isComposingRef.current) return false;

  const prepared = await preparePlanModeSubmit(data, {
    planModeEnabled,
    persistPlanMode,
    setPlanModeEnabled,
  });

  if (isPlanModeSubmitCancelled(prepared)) {
    return prepared;
  }

  if (!pendingPlanRevision) {
    return prepared;
  }

  const feedback = prepared.query.trim();
  if (!feedback) {
    return false;
  }

  setPendingPlanRevision(null);

  return {
    ...prepared,
    biz_params: {
      ...(prepared.biz_params || {}),
      mode: "plan",
      plan_interaction_response: {
        card_type: "plan_review",
        plan_id: pendingPlanRevision.planId,
        decision: "revise",
        feedback,
      },
    },
  };
};
```

Add `pendingPlanRevision` to the `useMemo` dependency list.

- [ ] **Step 6: Render active review card with callbacks**

In sender `beforeUI`, render:

```tsx
<>
  {taskProgressEnabled ? (
    <TaskProgressFloatingCard progress={taskProgress} />
  ) : null}
  <ActivePlanClarificationCard />
  <ActivePlanReviewCard
    onContinueModifying={handleContinueModifyingPlan}
    onPlanModeDecision={(enabled) => {
      void persistPlanMode(enabled);
    }}
  />
</>
```

Add `handleContinueModifyingPlan` and `persistPlanMode` to dependencies.

- [ ] **Step 7: Keep Plan Mode on for revise**

When pending revision is set, `setPlanModeEnabled(true)` is enough for local request mode. Do not call `persistPlanMode(true)` unless the current session metadata is false; otherwise avoid extra writes.

Use:

```ts
if (!planModeEnabled) {
  void persistPlanMode(true);
}
```

inside `handleContinueModifyingPlan` if product behavior requires cross-refresh persistence before the next message. Current confirmed behavior only requires keeping current Plan Mode active.

- [ ] **Step 8: Run tests**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx src/pages/Chat/index.test.tsx
```

Expected: PASS.

---

### Task 4: Make Execute And Exit Close Local Plan Mode With Animated Control Feedback

**Files:**
- Modify: `console/src/pages/Chat/planMode.tsx`
- Modify: `console/src/pages/Chat/index.module.less`
- Modify: `console/src/pages/Chat/index.tsx`
- Test: `console/src/pages/Chat/planMode.test.tsx`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Write failing tests for Plan Mode control fade-out**

In `planMode.test.tsx`, add:

```tsx
it("marks the active Plan Mode control as exiting when disabled after being visible", () => {
  const { rerender } = render(
    <ActivePlanModeControl
      enabled
      label="计划模式"
      displayLabel="计划"
      onDisable={vi.fn()}
    />,
  );

  expect(screen.getByRole("button", { name: "计划模式" })).toBeInTheDocument();

  rerender(
    <ActivePlanModeControl
      enabled={false}
      label="计划模式"
      displayLabel="计划"
      onDisable={vi.fn()}
    />,
  );

  expect(screen.getByRole("button", { name: "计划模式" })).toHaveAttribute(
    "data-plan-mode-exiting",
    "true",
  );
});
```

If the existing component is named `ActivePlanModeButton`, test that component instead of `ActivePlanModeControl`.

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/planMode.test.tsx
```

Expected: FAIL because disabled state currently returns `null` immediately.

- [ ] **Step 3: Add exit animation state**

Update `ActivePlanModeButton` in `planMode.tsx`:

```tsx
export function ActivePlanModeButton({
  enabled,
  disabled = false,
  label,
  displayLabel,
  onDisable,
}: {
  enabled: boolean;
  disabled?: boolean;
  label: string;
  displayLabel?: string;
  onDisable: () => void;
}) {
  const [rendered, setRendered] = React.useState(enabled);
  const [exiting, setExiting] = React.useState(false);

  React.useEffect(() => {
    if (enabled) {
      setRendered(true);
      setExiting(false);
      return;
    }

    if (rendered) {
      setExiting(true);
      const timer = window.setTimeout(() => {
        setRendered(false);
        setExiting(false);
      }, 180);
      return () => window.clearTimeout(timer);
    }
  }, [enabled, rendered]);

  if (!rendered) {
    return null;
  }

  return (
    <button
      type="button"
      className={styles.planModeActiveButton}
      aria-label={label}
      disabled={disabled || exiting}
      data-plan-mode-exiting={exiting ? "true" : undefined}
      onClick={onDisable}
    >
      <OrderedListOutlined className={styles.planModeActiveIcon} />
      <CloseCircleFilled className={styles.planModeCloseIcon} />
      <span>{displayLabel || label}</span>
    </button>
  );
}
```

- [ ] **Step 4: Add CSS animation**

In `console/src/pages/Chat/index.module.less`, add:

```less
.planModeActiveButton[data-plan-mode-exiting="true"] {
  pointer-events: none;
  animation: plan-mode-control-exit 180ms ease-in forwards;
}

@keyframes plan-mode-control-exit {
  from {
    opacity: 1;
    transform: translateY(0) scale(1);
    max-width: 96px;
  }

  to {
    opacity: 0;
    transform: translateY(3px) scale(0.96);
    max-width: 0;
  }
}
```

- [ ] **Step 5: Ensure execute and exit close local Plan Mode**

In `PlanReviewActiveCard`, when clicking `Execute` or `Exit Plan Mode`, call `onPlanModeDecision?.(false)` before emit. In `index.tsx`, pass:

```tsx
onPlanModeDecision={(enabled) => {
  setPlanModeEnabled(enabled);
  void persistPlanMode(enabled);
}}
```

This means the button starts fading immediately while backend persistence completes.

- [ ] **Step 6: Run tests**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/planMode.test.tsx src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: PASS.

---

### Task 5: Verify Empty Short-Circuit SSE Does Not Need A Chat Message

**Files:**
- Modify only if needed: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.tsx`
- Test: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.test.tsx`

- [ ] **Step 1: Inspect current behavior**

Current `useChatRequest` already finishes on terminal empty response frames. The `exit_plan` backend returns:

```json
{
  "object": "response",
  "status": "completed",
  "type": "exit_plan",
  "chat_id": "..."
}
```

Because confirmed product behavior says no chat message should be added, do not add an assistant output for this frame.

- [ ] **Step 2: Add regression test only if current tests do not cover `type=exit_plan`**

Add to `useChatRequest.test.tsx`:

```tsx
it("finishes exit_plan short-circuit frames without rendering a chat message", async () => {
  mocks.fetch.mockResolvedValue({
    ok: true,
    body: {},
  } as Response);
  mocks.streamChunks[1] = {
    data: JSON.stringify({
      object: "response",
      id: "response-1",
      status: "completed",
      type: "exit_plan",
      created_at: 1,
      completed_at: 2,
      output: [],
    }),
  };

  const updateMessage = vi.fn();
  const onFinish = vi.fn();
  const currentQARef = {
    current: {
      response: {
        id: "ui-response-a",
        msgStatus: "generating",
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response-1",
              status: "created",
              created_at: 0,
              output: [],
            },
          },
        ],
      },
      activeRequestOwner: createOwner(),
    },
  } as CurrentQARef;

  render(
    <Harness
      currentQARef={currentQARef}
      updateMessage={updateMessage}
      onFinish={onFinish}
    />,
  );

  const requestPromise = hookApi.request([], undefined, createOwner());
  mocks.streamGate.resolve();

  await act(async () => {
    await requestPromise;
  });

  const responseCardData = currentQARef.current.response?.cards?.[0]
    ?.data as { output?: unknown[]; status?: string };

  expect(responseCardData.status).toBe("completed");
  expect(responseCardData.output).toEqual([]);
  expect(onFinish).toHaveBeenCalledWith(createOwner());
});
```

- [ ] **Step 3: Run the request hook test**

Run:

```bash
cd console && pnpm test:run src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.test.tsx
```

Expected: PASS. If it fails because terminal empty frames are not updating consistently, make the smallest fix in `useChatRequest.tsx` without rendering visible assistant content.

---

### Task 6: Final Verification

**Files:**
- No new implementation files.

- [ ] **Step 1: Run focused frontend tests**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx src/pages/Chat/sessionApi/index.test.ts src/pages/Chat/planMode.test.tsx src/pages/Chat/index.test.tsx src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run relevant backend tests to guard existing decision protocol**

Run:

```bash
venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py -q
```

Expected: PASS.

- [ ] **Step 3: Run GitNexus change detection before commit**

Run:

```text
mcp__gitnexus.detect_changes({
  repo: "CoPaw",
  scope: "all"
})
```

Expected: affected scope is limited to Console Plan Interaction / Plan Mode frontend files and the already-approved documentation glossary updates.

- [ ] **Step 4: Review manual UI scenarios**

Verify in browser:

```text
1. Enter Plan Mode and produce a Proposed Plan.
2. Reload the session.
3. Confirm the historical plan remains as a read-only snapshot.
4. Confirm only the latest active plan review appears near the composer.
5. Click Continue modifying.
6. Confirm Plan Mode stays active and the input is ready for revision text.
7. Submit revision text.
8. Confirm the old snapshot shows 已要求修改 and the next request carries decision=revise.
9. Produce another Proposed Plan.
10. Click Execute.
11. Confirm Plan Mode control fades out and execution continues normally.
12. Produce another Proposed Plan.
13. Click Exit Plan Mode.
14. Confirm no chat message is added and the Plan Mode control fades out.
15. Use a long summary and confirm it wraps within card width.
```

- [ ] **Step 5: Commit**

Only commit files changed for this plan. Do not include unrelated working tree changes.

```bash
git add CONTEXT.md \
  console/src/pages/Chat/messageMeta.ts \
  console/src/pages/Chat/sessionApi/index.ts \
  console/src/pages/Chat/components/PlanInteractionCards.tsx \
  console/src/pages/Chat/components/PlanInteractionCards.module.less \
  console/src/pages/Chat/planMode.tsx \
  console/src/pages/Chat/index.tsx \
  console/src/pages/Chat/components/PlanInteractionCards.test.tsx \
  console/src/pages/Chat/sessionApi/index.test.ts \
  console/src/pages/Chat/planMode.test.tsx \
  console/src/pages/Chat/index.test.tsx \
  console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.test.tsx \
  docs/superpowers/plans/2026-07-03-plan-review-active-card.md
git commit -m "fix(console): make plan review cards active-only"
```

If `useChatRequest.test.tsx` is unchanged, omit it from `git add`.

---

## Self-Review

- Spec coverage:
  - Historical card replay fixed by active-only rendering and read-only snapshots.
  - `Exit Plan Mode` fixed through local Plan Mode control close and no chat-message output.
  - `Continue modifying` fixed through deferred Plan Revision Input.
  - `summary` wrapping fixed by moving it to a body block.

- Placeholder scan:
  - No task uses `TBD`, `TODO`, or unspecified error handling.
  - Each implementation task names exact files and test commands.

- Type consistency:
  - `PlanReviewDecision` uses `revise | execute | exit_plan`.
  - `submitted_decision` and `feedback` are added consistently to `ChatPlanReviewCardData`.
  - Pending revision state stores `planId` and maps it to `plan_interaction_response.plan_id`.
