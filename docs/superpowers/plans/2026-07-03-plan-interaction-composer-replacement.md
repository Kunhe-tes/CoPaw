# Plan Interaction Composer Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the latest active Plan Interaction Card as a blocking replacement for the normal chat composer, and make top-level choice clarifications always accept custom text.

**Architecture:** Keep backend Plan Interaction metadata unchanged. Add a generic Console sender render hook that lets Chat replace only the default composer while preserving surrounding sender UI such as task progress and disclaimer. Consolidate active Plan Interaction discovery so exactly one latest non-superseded card owns the composer replacement.

**Tech Stack:** React, TypeScript, CSS modules, Vitest, Testing Library, existing ChatAnywhere sender options, existing Plan Interaction event emitter.

---

## Resolved Product Decisions

- `ask_plan_clarification` and `submit_proposed_plan` replace the whole main composer panel while active: text input, send button, attachments, quick menu, and Plan Mode prefix controls are not visible or usable.
- A completed local card action immediately removes the replacement and restores the appropriate UI; it does not wait for backend confirmation.
- `Continue modifying` on a Proposed Plan keeps the existing **Plan Revision Input** flow: the card disappears, normal composer returns, and the next user-authored message carries `decision=revise`.
- `ask_plan_clarification` dismissal closes only the current clarification and restores the normal composer; Plan Mode remains enabled and no `plan_interaction_response` is submitted.
- If multiple Plan Interaction Cards are present, the latest non-superseded card in message timeline is the only active card.
- Chat history may preserve context snapshots, but only the composer replacement has active controls.
- Top-level `single_choice` and `multi_choice` clarification cards always show a custom text input. This is a frontend default; do not change `ask_plan_clarification` backend defaults or tool schema.
- Top-level `form` clarification fields do not receive field-level custom choice text by default.
- Custom text submits as `text`; do not synthesize a fake option id.
- In `single_choice`, non-empty custom text and a selected option are mutually exclusive.
- In `multi_choice`, custom text can be submitted alone or together with selected options.
- Custom text supports `Enter` to submit, `Shift+Enter` for newline, and IME composing protection.
- No ADR is required for this change. `CONTEXT.md` already contains the resolved terms.

## File Structure

- Modify `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/types/IChatAnywhere.ts`
  - Add a sender `renderComposer` hook that receives the default composer element.
- Modify `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.tsx`
  - Build the current `ChatInput` as `defaultComposer`.
  - Render `sender.renderComposer(defaultComposer)` when provided.
  - Keep `beforeUI` and `afterUI` outside the composer render hook.
- Modify `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.test.tsx`
  - Verify `renderComposer` can replace the input, attachment quick menu, prefix, and submit button.
  - Verify normal composer still renders when `renderComposer` returns `defaultComposer`.
- Modify `console/src/pages/Chat/components/PlanInteractionCards.tsx`
  - Add a unified active-card finder.
  - Add `ActivePlanInteractionComposer` that returns either the active card or the supplied default composer.
  - Change Plan Review `revise` to locally complete the active review card after registering pending revision input.
  - Make top-level choice clarification custom text always visible.
- Modify `console/src/pages/Chat/components/PlanInteractionCards.module.less`
  - Add spacing rules for the composer replacement card if needed.
  - Add always-visible custom text styling that fits inside the existing card.
- Modify `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
  - Cover latest-card selection, composer replacement fallback, Plan Review revise completion, and custom text semantics.
- Modify `console/src/pages/Chat/index.tsx`
  - Move `ActivePlanClarificationCard` and `ActivePlanReviewCard` out of `sender.beforeUI`.
  - Pass `renderComposer` that wraps the default composer with `ActivePlanInteractionComposer`.
- Modify `console/src/pages/Chat/index.test.tsx`
  - Update mocks and assertions for `sender.renderComposer`.

## GitNexus Safety Notes

Before editing implementation symbols, run GitNexus impact analysis for each target symbol. Known likely targets:

```text
PlanClarificationCard
PlanReviewCard
ActivePlanClarificationCard
ActivePlanReviewCard
Input
IAgentScopeRuntimeWebUISenderOptions
```

If GitNexus reports a HIGH or CRITICAL risk for a symbol, stop and report the direct callers, affected flows, and risk before editing. If TSX component symbols are not indexed, record that result in the implementation notes and use the focused Vitest files listed below as the primary guard.

## Task 1: Add A Generic Composer Render Hook

**Files:**
- Modify: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/types/IChatAnywhere.ts`
- Modify: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.tsx`
- Test: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.test.tsx`

- [ ] **Step 1: Run impact analysis**

Run GitNexus impact for `Input` and `IAgentScopeRuntimeWebUISenderOptions`. Expected risk is not HIGH or CRITICAL.

- [ ] **Step 2: Write failing tests for composer replacement**

Add these tests to `Input/index.test.tsx`:

```tsx
it("lets sender.renderComposer replace the default composer controls", () => {
  senderOptions.current = {
    prefix: <button type="button">计划模式</button>,
    quickMenuItems: [<button key="custom" type="button">自定义菜单</button>],
    renderComposer: vi.fn(() => (
      <section data-testid="composer-replacement">
        <button type="button">提交卡片</button>
      </section>
    )),
  };

  render(<Input onCancel={vi.fn()} onSubmit={vi.fn()} />);

  expect(screen.getByTestId("composer-replacement")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "提交卡片" })).toBeInTheDocument();
  expect(screen.queryByTestId("chat-input")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "快捷操作", hidden: true })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "计划模式", hidden: true })).not.toBeInTheDocument();
  expect(senderOptions.current.renderComposer).toHaveBeenCalledTimes(1);
});

it("keeps the normal composer when sender.renderComposer returns the default composer", () => {
  senderOptions.current = {
    renderComposer: vi.fn((defaultComposer: React.ReactElement) => defaultComposer),
  };

  render(<Input onCancel={vi.fn()} onSubmit={vi.fn()} />);

  expect(screen.getByTestId("chat-input")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "submit", hidden: true })).toBeInTheDocument();
});
```

- [ ] **Step 3: Run the focused test and verify failure**

Run:

```bash
cd console && pnpm test:run src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.test.tsx
```

Expected: FAIL because `renderComposer` is not yet part of sender options and `Input` always renders `ChatInput`.

- [ ] **Step 4: Extend sender options**

In `IChatAnywhere.ts`, add the property below next to `beforeUI` / `afterUI`:

```ts
  /**
   * @description 自定义渲染输入框主体，可用来用阻塞式交互卡片替换默认输入框
   * @descriptionEn Custom renderer for the main composer body, useful for replacing the default composer with a blocking interaction card
   */
  renderComposer?: (defaultComposer: React.ReactElement) => React.ReactElement;
```

- [ ] **Step 5: Render through the hook**

In `Input/index.tsx`, destructure `renderComposer` from `senderOptions`, build the existing `ChatInput` as `defaultComposer`, then render:

```tsx
  const defaultComposer = (
    <ChatInput
      loading={inputContext.loading}
      disabled={inputContext.disabled}
      placeholder={placeholder}
      value={content}
      prefix={
        <>
          <ComposerQuickMenu
            disabled={Boolean(inputContext.disabled)}
            triggerLabel={t("chat.quickMenu.trigger", "快捷操作")}
          >
            {mergedQuickMenuItems}
          </ComposerQuickMenu>
          {prefix}
        </>
      }
      header={fileList.length > 0 ? uploadFileListHeader : undefined}
      onChange={handleContentChange}
      maxLength={maxLength}
      onSubmit={handleSubmit}
      onCancel={handleCancel}
      allowSpeech={allowSpeech}
      onPasteFile={canHandlePasteFile}
      suggestions={suggestions}
    />
  );
  const renderedComposer = renderComposer
    ? renderComposer(defaultComposer)
    : defaultComposer;
```

Then replace the inline `<ChatInput ... />` in the return block with `{renderedComposer}`.

- [ ] **Step 6: Run the focused test and verify pass**

Run:

```bash
cd console && pnpm test:run src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.test.tsx
```

Expected: PASS.

## Task 2: Consolidate Active Plan Interaction Selection

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Run impact analysis**

Run GitNexus impact for `ActivePlanClarificationCard`, `ActivePlanReviewCard`, and `PlanReviewCard`. Expected risk is not HIGH or CRITICAL.

- [ ] **Step 2: Write failing tests for latest-card ownership**

Add tests to `PlanInteractionCards.test.tsx`:

```tsx
function renderActiveComposer(messages: IAgentScopeRuntimeWebUIMessage<unknown>[]) {
  return render(
    <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
      <ChatAnywhereMessagesContext.Provider
        value={{
          messages,
          setMessages: vi.fn(),
          getMessages: () => messages,
        }}
      >
        <ActivePlanInteractionComposer
          defaultComposer={<div data-testid="default-composer">composer</div>}
        />
      </ChatAnywhereMessagesContext.Provider>
    </ChatAnywhereSessionsContext.Provider>,
  );
}

it("replaces the composer with the latest active plan interaction card", () => {
  renderActiveComposer([
    createClarificationMessage({
      messageId: "assistant-clarification",
      originalId: "original-1",
      traceId: "trace-1",
      prompt: "Pick scope",
    }),
    createReviewMessage({
      messageId: "assistant-review",
      cardId: "plan-2",
      title: "Review latest plan",
    }),
  ]);

  expect(screen.queryByTestId("default-composer")).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Review latest plan" })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Pick scope" })).not.toBeInTheDocument();
});

it("falls back to the default composer when no active plan interaction exists", () => {
  renderActiveComposer([
    createReviewMessage({
      messageId: "assistant-review",
      cardId: "plan-2",
      title: "Submitted plan",
      status: "submitted",
      submittedDecision: "execute",
    }),
  ]);

  expect(screen.getByTestId("default-composer")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Submitted plan" })).not.toBeInTheDocument();
});
```

Update the import list in the test file to include `ActivePlanInteractionComposer`.

- [ ] **Step 3: Run the focused test and verify failure**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: FAIL because `ActivePlanInteractionComposer` does not exist.

- [ ] **Step 4: Add a unified active-card finder**

In `PlanInteractionCards.tsx`, add:

```tsx
type ActivePlanInteraction =
  | {
      type: "clarification";
      data: ChatPlanClarificationCardData;
      instanceKey: string;
      sourceKey: string | null;
    }
  | {
      type: "review";
      data: ChatPlanReviewCardData;
      instanceKey: string;
    };

function findLatestActivePlanInteractionCard(
  messages: IAgentScopeRuntimeWebUIMessage[],
): ActivePlanInteraction | null {
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
      if (card.code !== PLAN_INTERACTION_CARD_CODE || hasLaterUserMessage) {
        continue;
      }

      const instanceKey = `${message.id}:${card.id || card.code}:${cardIndex}`;
      if (isPlanReviewCardData(card.data) && card.data.status !== "submitted") {
        return {
          type: "review",
          data: card.data,
          instanceKey,
        };
      }

      if (isPlanClarificationCardData(card.data)) {
        return {
          type: "clarification",
          data: card.data,
          instanceKey,
          sourceKey: resolveClarificationSourceKey(cards, card.data),
        };
      }
    }
  }
  return null;
}
```

- [ ] **Step 5: Add the composer replacement component**

Add:

```tsx
export function ActivePlanInteractionComposer({
  defaultComposer,
  onContinueModifying,
  onPlanModeDecision,
}: {
  defaultComposer: React.ReactElement;
  onContinueModifying?: (data: ChatPlanReviewCardData) => void;
  onPlanModeDecision?: (enabled: boolean) => void;
}) {
  const interaction = useContextSelector(ChatAnywhereMessagesContext, (value) =>
    findLatestActivePlanInteractionCard(value.messages || []),
  );

  if (!interaction) {
    return defaultComposer;
  }

  if (interaction.type === "review") {
    return (
      <PlanReviewCard
        active
        data={interaction.data}
        cardInstanceKey={interaction.instanceKey}
        onContinueModifying={onContinueModifying}
        onPlanModeDecision={onPlanModeDecision}
      />
    );
  }

  return (
    <PlanClarificationCard
      data={interaction.data}
      cardInstanceKey={interaction.instanceKey}
    />
  );
}
```

Keep the existing exported `ActivePlanClarificationCard` and `ActivePlanReviewCard` until all call sites and tests are migrated.

- [ ] **Step 6: Make Plan Review revise complete locally**

In `PlanReviewActiveCard.handleDecision`, update the `revise` branch:

```tsx
    if (decision === "revise") {
      onContinueModifying?.(data);
      setSubmitted(true);
      return;
    }
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: PASS after updating any old active-card assertions to use `ActivePlanInteractionComposer` where the test is about composer ownership.

## Task 3: Make Top-Level Choice Clarification Custom Text Always Visible

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Run impact analysis**

Run GitNexus impact for `PlanClarificationCard`. Expected risk is not HIGH or CRITICAL.

- [ ] **Step 2: Write failing tests for custom text defaults**

Add tests to `PlanInteractionCards.test.tsx`:

```tsx
it("shows a custom text box by default for top-level single choice cards", () => {
  render(
    <PlanClarificationCard
      data={{
        card_type: "plan_clarification",
        kind: "single_choice",
        prompt: "Pick scope",
        options: [{ id: "small", label: "Small" }],
      }}
    />,
  );

  expect(screen.getByRole("textbox", { name: "Pick scope" })).toBeInTheDocument();
});

it("single choice custom text clears the selected option and submits only text", async () => {
  const events = captureSubmitEvents();
  render(
    <PlanClarificationCard
      data={{
        card_type: "plan_clarification",
        kind: "single_choice",
        prompt: "Pick scope",
        options: [{ id: "small", label: "Small" }],
      }}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /Small/ }));
  fireEvent.change(screen.getByRole("textbox", { name: "Pick scope" }), {
    target: { value: "Use a narrower module" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交" }));

  await waitFor(() => expect(events.handler).toHaveBeenCalledTimes(1));
  expect(events.handler.mock.calls[0][0].detail.biz_params.plan_interaction_response).toMatchObject({
    card_type: "plan_clarification",
    kind: "single_choice",
    selected_option_ids: [],
    text: "Use a narrower module",
  });
  events.cleanup();
});

it("single choice selecting an option clears custom text", () => {
  render(
    <PlanClarificationCard
      data={{
        card_type: "plan_clarification",
        kind: "single_choice",
        prompt: "Pick scope",
        options: [{ id: "small", label: "Small" }],
      }}
    />,
  );

  const textbox = screen.getByRole("textbox", { name: "Pick scope" }) as HTMLTextAreaElement;
  fireEvent.change(textbox, { target: { value: "Custom scope" } });
  fireEvent.click(screen.getByRole("button", { name: /Small/ }));

  expect(textbox.value).toBe("");
});

it("multi choice submits selected options together with custom text", async () => {
  const events = captureSubmitEvents();
  render(
    <PlanClarificationCard
      data={{
        card_type: "plan_clarification",
        kind: "multi_choice",
        prompt: "Pick checks",
        options: [
          { id: "unit", label: "Unit tests" },
          { id: "lint", label: "Lint" },
        ],
      }}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /Unit tests/ }));
  fireEvent.change(screen.getByRole("textbox", { name: "Pick checks" }), {
    target: { value: "Also run smoke test" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交" }));

  await waitFor(() => expect(events.handler).toHaveBeenCalledTimes(1));
  expect(events.handler.mock.calls[0][0].detail.biz_params.plan_interaction_response).toMatchObject({
    card_type: "plan_clarification",
    kind: "multi_choice",
    selected_option_ids: ["unit"],
    text: "Also run smoke test",
  });
  events.cleanup();
});

it("multi choice allows submitting only custom text", async () => {
  const events = captureSubmitEvents();
  render(
    <PlanClarificationCard
      data={{
        card_type: "plan_clarification",
        kind: "multi_choice",
        prompt: "Pick checks",
        options: [{ id: "unit", label: "Unit tests" }],
      }}
    />,
  );

  fireEvent.change(screen.getByRole("textbox", { name: "Pick checks" }), {
    target: { value: "Manual QA only" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交" }));

  await waitFor(() => expect(events.handler).toHaveBeenCalledTimes(1));
  expect(events.handler.mock.calls[0][0].detail.biz_params.plan_interaction_response).toMatchObject({
    card_type: "plan_clarification",
    kind: "multi_choice",
    selected_option_ids: [],
    text: "Manual QA only",
  });
  events.cleanup();
});
```

- [ ] **Step 3: Run the focused test and verify failure**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: FAIL because custom text is currently gated by `allow_custom_response` and hidden behind a row activation path.

- [ ] **Step 4: Change top-level custom text derivation**

In `PlanClarificationCard`, replace the current `allowsCustomText` derivation with:

```tsx
  const isTopLevelChoice =
    data.kind === "single_choice" || data.kind === "multi_choice";
  const allowsCustomText =
    data.kind === "text" ||
    isTopLevelChoice ||
    data.allow_custom_response === true;
```

Replace custom text selection state so top-level choices do not need `customActive` to show the text area. Keep `customActive` only if existing form supplement behavior still needs it, or remove it if all tests pass without it.

- [ ] **Step 5: Render the text box under top-level choices**

Set:

```tsx
  const showChoiceRows =
    data.kind === "single_choice" ||
    data.kind === "multi_choice" ||
    activeField?.type === "single_choice" ||
    activeField?.type === "multi_choice";
  const showTopLevelChoiceCustomInput = isTopLevelChoice;
  const showCustomInput =
    data.kind === "text" || showTopLevelChoiceCustomInput || isSupplementStep;
```

When rendering `ChoiceRows`, do not add the old synthetic custom option for top-level choices:

```tsx
          <ChoiceRows
            options={activeOptions}
            selectedIds={activeSelectedIds}
            focusedIndex={focusedIndex}
            allowCustomResponse={false}
            customActive={false}
            onFocusIndexChange={setFocusedIndex}
            onSelect={selectActiveOption}
          />
```

Use this placeholder for top-level choice custom text:

```tsx
            placeholder={
              data.kind === "text"
                ? data.prompt
                : isTopLevelChoice
                ? "输入自定义回复"
                : "请输入自定义回复"
            }
```

- [ ] **Step 6: Enforce single-choice exclusivity**

When custom text changes:

```tsx
  const handleCustomTextChange = (value: string) => {
    setTextInput(value);
    if (data.kind === "single_choice" && value.trim()) {
      setSingleChoice("");
    }
  };
```

Use `onChange={(event) => handleCustomTextChange(event.target.value)}` for the custom textarea.

In `selectActiveOption`, keep the existing top-level behavior that clears text when a non-form option is selected:

```tsx
    if (!activeField) {
      setTextInput("");
    }
```

- [ ] **Step 7: Adjust disabled and payload behavior**

For top-level choices, compute:

```tsx
  const effectiveChoiceText = trimmedText;
```

Keep `disabled` equivalent to:

```tsx
  const disabled =
    data.kind === "text"
      ? !trimmedText
      : data.kind === "form"
      ? !requiredFormFieldsSatisfied ||
        [...formQueryLines, trimmedText].filter(Boolean).length === 0
      : selectedIds.length === 0 && !trimmedText;
```

The existing payload shape should remain:

```tsx
{
  card_type: "plan_clarification",
  kind: data.kind,
  selected_option_ids: effectiveSelectedIds,
  text: effectiveText || undefined,
}
```

- [ ] **Step 8: Update keyboard row count**

For top-level choices, remove the old custom row from keyboard navigation:

```tsx
    const rowCount = activeOptions.length;
```

Keep text-target `Enter` behavior unchanged so the textarea can submit with IME protection.

- [ ] **Step 9: Run focused tests**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: PASS.

## Task 4: Wire Composer Replacement Into Chat Page

**Files:**
- Modify: `console/src/pages/Chat/index.tsx`
- Test: `console/src/pages/Chat/index.test.tsx`

- [ ] **Step 1: Run impact analysis**

Run GitNexus impact for the Chat page symbols around `options`, `handleContinueModifyingPlan`, and `handlePlanModeDecision`. Expected risk is not HIGH or CRITICAL.

- [ ] **Step 2: Update Chat page tests**

In `Chat/index.test.tsx`, update the `PlanInteractionCards` mock to export `ActivePlanInteractionComposer`:

```tsx
ActivePlanInteractionComposer: ({
  defaultComposer,
}: {
  defaultComposer: React.ReactElement;
}) => defaultComposer,
```

Add an assertion in the options-capture test that `sender.beforeUI` does not include active Plan Interaction cards and `sender.renderComposer` exists:

```tsx
expect(mocks.capturedOptions?.sender?.renderComposer).toEqual(expect.any(Function));
```

If the existing test renders `sender.beforeUI`, keep it focused on `TaskProgressFloatingCard` only.

- [ ] **Step 3: Run Chat page tests and verify failure**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/index.test.tsx
```

Expected: FAIL until `renderComposer` is wired.

- [ ] **Step 4: Replace active card mounting**

In `Chat/index.tsx`, import `ActivePlanInteractionComposer` and remove `ActivePlanClarificationCard` / `ActivePlanReviewCard` from the active sender UI.

Change `sender.beforeUI` to keep only non-composer replacement UI:

```tsx
        beforeUI: (
          <>
            {taskProgressEnabled ? (
              <TaskProgressFloatingCard progress={taskProgress} />
            ) : null}
          </>
        ),
```

Add `renderComposer` to `sender`:

```tsx
        renderComposer: (defaultComposer) => (
          <ActivePlanInteractionComposer
            defaultComposer={defaultComposer}
            onContinueModifying={handleContinueModifyingPlan}
            onPlanModeDecision={handlePlanModeDecision}
          />
        ),
```

- [ ] **Step 5: Run Chat page tests**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/index.test.tsx
```

Expected: PASS.

## Task 5: Run Regression Suite And Detect Affected Scope

**Files:**
- No new implementation files.
- Validate changed files from Tasks 1-4.

- [ ] **Step 1: Run focused Console tests**

Run:

```bash
cd console && pnpm test:run src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.test.tsx src/pages/Chat/components/PlanInteractionCards.test.tsx src/pages/Chat/index.test.tsx src/pages/Chat/messageMeta.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run typecheck or broader frontend test command if available**

Inspect `console/package.json`. If it defines a typecheck script, run it. Otherwise run the existing test command:

```bash
cd console && pnpm test:run
```

Expected: PASS, or report unrelated pre-existing failures with exact failing test names.

- [ ] **Step 3: Run GitNexus change detection before committing**

Run:

```text
mcp__gitnexus.detect_changes({ repo: "CoPaw", scope: "all" })
```

Expected affected scope: Chat input rendering, Plan Interaction card rendering, and Chat page sender option wiring. Unexpected backend, provider, tenant, or security flow changes should be investigated before commit.

- [ ] **Step 4: Commit**

Commit only the files changed for this plan:

```bash
git add CONTEXT.md docs/superpowers/plans/2026-07-03-plan-interaction-composer-replacement.md console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/types/IChatAnywhere.ts console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.tsx console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.test.tsx console/src/pages/Chat/components/PlanInteractionCards.tsx console/src/pages/Chat/components/PlanInteractionCards.module.less console/src/pages/Chat/components/PlanInteractionCards.test.tsx console/src/pages/Chat/index.tsx console/src/pages/Chat/index.test.tsx
git commit -m "feat(console): replace composer with active plan cards"
```

## Self-Review

- Spec coverage: The plan covers composer replacement, one latest active card, Plan Review revise restoration, Planning Clarification dismissal behavior, top-level choice custom text, payload shape, and tests.
- Backend protocol check: The plan does not change `src/swe/agents/tools/planning.py`, `src/swe/app/plans/models.py`, or backend tests.
- ADR check: No ADR is created because the decision is reversible and Console-scoped.
- Placeholder scan: The plan uses concrete file paths, commands, and expected results. No implementation step depends on unspecified backend work.
