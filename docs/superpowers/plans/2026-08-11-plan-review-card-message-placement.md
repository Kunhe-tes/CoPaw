# Plan Review Card Message Placement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place an active `submit_proposed_plan` review card immediately after its source assistant message, rather than replacing the chat composer.

**Architecture:** A small plan-review render context will carry the existing decision callbacks from `ChatPage` into the static Chat card registry. The registry renders `plan_review` cards through a `PlanReviewMessageCard` wrapper, while the composer keeps `ActivePlanInteractionComposer` only for plan-clarification cards; submitted plan reviews remain snapshots through the existing card component.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, AgentScope Chat runtime.

---

### Task 1: Lock in message-flow rendering with a failing page test

**Files:**
- Modify: `console/src/pages/Chat/index.test.tsx:510-550, 1133-1170`

- [ ] **Step 1: Replace the mocked card component with a visible review-card probe.**

```tsx
PlanReviewMessageCard: () => (
  <div data-testid="plan-review-message-card" />
),
```

- [ ] **Step 2: Replace the obsolete assertions with the desired message-renderer assertion.**

```tsx
it("renders an active plan review card in the message flow", () => {
  render(<ChatPage />);
  const renderer = mocks.capturedOptions?.cards?.PlanInteraction;

  const card = renderer?.({
    data: {
      card_type: "plan_review",
      plan_id: "plan-123",
      title: "Implementation plan",
      summary: "Plan summary",
      steps: [],
      risks: [],
      verification: [],
    },
  });
  render(<>{card}</>);

  expect(screen.getByTestId("plan-review-message-card")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run the targeted test and confirm it fails because `PlanInteraction` still returns `null`.**

Run: `cd console && pnpm test:run src/pages/Chat/index.test.tsx`

Expected: FAIL on `renders an active plan review card in the message flow` because `PlanInteraction` still returns `null`.

### Task 2: Add a narrow context for message-card actions

**Files:**
- Create: `console/src/pages/Chat/planReviewRenderContext.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx:1-20, 1043-1070`

- [ ] **Step 1: Write a failing component test that mounts `PlanReviewMessageCard` inside a provider and expects the active card.**

```tsx
render(
  <ChatPlanReviewRenderProvider value={callbacks}>
    <PlanReviewMessageCard data={createReviewData()} />
  </ChatPlanReviewRenderProvider>,
);

expect(screen.getByTestId("active-plan-review-card")).toBeInTheDocument();
```

- [ ] **Step 2: Run the targeted component test and confirm it fails because `PlanReviewMessageCard` does not exist.**

Run: `cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx`

Expected: FAIL because the message-card wrapper is missing.

- [ ] **Step 3: Create the context and wrapper, passing existing callbacks to the active `PlanReviewCard`.**

```tsx
export function PlanReviewMessageCard({
  data,
}: {
  data: ChatPlanReviewCardData;
}) {
  const { onContinueModifying, onPlanModeDecision } =
    useChatPlanReviewRenderContext();
  return (
    <PlanReviewCard
      active={data.status !== "submitted"}
      data={data}
      cardInstanceKey={data.plan_id}
      onContinueModifying={onContinueModifying}
      onPlanModeDecision={onPlanModeDecision}
    />
  );
}
```

- [ ] **Step 4: Re-run the component test and confirm it passes.**

Run: `cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx`

Expected: PASS.

### Task 3: Use the wrapper in the Chat registry and keep the composer for clarifications

**Files:**
- Modify: `console/src/pages/Chat/index.tsx:127, 213-222, 1913-1935, 2119-2126, 2283-2344`

- [ ] **Step 1: Import `PlanReviewMessageCard` and the new provider, then replace the `PlanInteraction` null renderer with a plan-review guard.**

```tsx
function isPlanReviewCardData(
  data: unknown,
): data is ChatPlanReviewCardData {
  return Boolean(data) && typeof data === "object" &&
    (data as { card_type?: unknown }).card_type === "plan_review";
}

const chatCardRenderers = {
  PlanInteraction: (props: { data: unknown }) =>
    isPlanReviewCardData(props.data) ? (
      <PlanReviewMessageCard data={props.data} />
    ) : null,
};
```

- [ ] **Step 2: Memoize the two existing callbacks into the provider value and wrap the existing Chat UI subtree with `ChatPlanReviewRenderProvider`.**

```tsx
const planReviewRenderContextValue = useMemo(
  () => ({ onContinueModifying: handleContinueModifyingPlan,
           onPlanModeDecision: handlePlanModeDecision }),
  [handleContinueModifyingPlan, handlePlanModeDecision],
);
```

- [ ] **Step 3: Keep `ActivePlanInteractionComposer` in `sender.renderComposer` for clarifications only; the existing callback props may remain for compatibility but must no longer cause a review card to replace the composer.**

```tsx
renderComposer: (defaultComposer) => (
  <ActivePlanInteractionComposer
    defaultComposer={defaultComposer}
    onContinueModifying={handleContinueModifyingPlan}
    onPlanModeDecision={handlePlanModeDecision}
  />
),
```

- [ ] **Step 4: Run the page test and confirm it passes.**

Run: `cd console && pnpm test:run src/pages/Chat/index.test.tsx`

Expected: PASS.

### Task 4: Update component tests for the new composer responsibility

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx:1407-1450`

- [ ] **Step 1: Replace plan-review composer-selection tests with an assertion that the composer remains the default for a plan review.**

```tsx
it("keeps the default composer when a plan review is pending", () => {
  renderActiveComposer([createReviewMessage({ messageId: "message-1" })]);

  expect(screen.getByTestId("default-composer")).toBeInTheDocument();
  expect(screen.queryByTestId("active-plan-review-card")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the component test and confirm it fails until review selection is removed from `ActivePlanInteractionComposer`.**

Run: `cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx`

Expected: FAIL because the active review replaces the composer.

- [ ] **Step 3: Remove `findLatestPlanReviewCard`, `ActivePlanReviewCard`, and the review branch from `findLatestActivePlanInteractionCard` and its `ActivePlanInteraction` union, leaving plan clarification as the sole composer interaction.**

```tsx
type ActivePlanInteraction = {
  type: "clarification";
  data: ChatPlanClarificationCardData;
  instanceKey: string;
  sourceKey: string | null;
};
```

- [ ] **Step 4: Re-run the component test and confirm it passes.**

Run: `cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx`

Expected: PASS.

### Task 5: Verify the changed Console surface

**Files:**
- Verify: `console/src/pages/Chat/index.tsx`
- Verify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`

- [ ] **Step 1: Run all directly affected tests.**

Run: `cd console && pnpm test:run src/pages/Chat/index.test.tsx src/pages/Chat/components/PlanInteractionCards.test.tsx`

Expected: PASS with no failures.

- [ ] **Step 2: Run the Console build to type-check the card registry and UI.**

Run: `cd console && pnpm build`

Expected: successful production build.

- [ ] **Step 3: Inspect the diff and confirm it contains only Chat card placement, its tests, and the two planning documents.**

Run: `git diff --check && git diff -- console/src/pages/Chat/index.tsx console/src/pages/Chat/components/PlanInteractionCards.tsx console/src/pages/Chat/index.test.tsx console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

Expected: no whitespace errors and no unrelated production changes.
