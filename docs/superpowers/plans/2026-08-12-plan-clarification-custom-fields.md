# Plan Clarification Custom Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make choice clarifications support default, field-level custom answers and keep long option content readable in the compact card.

**Architecture:** Retain business choice IDs in `field_values` and add `custom_field_values` only for non-empty field-level custom text. The backend defaults the opt-in flag, while the Console owns the system “自定义填写” row, field state and display behavior. No plan persistence or Plan Review contract changes are required.

**Tech Stack:** Python, Pydantic, pytest, React 18, TypeScript, Less CSS Modules, Vitest, Testing Library.

---

## File Structure

- `src/swe/agents/tools/planning.py`: tool signature and tool-facing instructions for default custom choice behavior.
- `src/swe/app/plans/models.py`: serialized card default for `allow_custom_response`.
- `src/swe/agents/react_agent.py`: Plan Mode instruction telling the model not to generate an “other” option.
- `tests/unit/agents/tools/test_planning.py`: tool defaults and explicit opt-out regression tests.
- `tests/unit/app/plans/test_models.py`: model default regression test.
- `console/src/pages/Chat/messageMeta.ts`: optional payload metadata remains backward-compatible when the flag is absent.
- `console/src/pages/Chat/messageMeta.test.ts`: legacy card default compatibility test.
- `console/src/pages/Chat/components/PlanInteractionCards.tsx`: field-level custom state, completion, payload and query rendering.
- `console/src/pages/Chat/components/PlanInteractionCards.module.less`: custom field input and long option wrapping/scroll behavior.
- `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`: user-visible submission, validation, display and style contracts.

### Task 1: Make custom response opt-out rather than opt-in

**Files:**
- Modify: `src/swe/agents/tools/planning.py:345-377`
- Modify: `src/swe/app/plans/models.py:208-232`
- Modify: `src/swe/agents/react_agent.py:121-133`
- Test: `tests/unit/agents/tools/test_planning.py`
- Test: `tests/unit/app/plans/test_models.py`

- [ ] **Step 1: Run required impact analysis**

Run GitNexus impact for `ask_plan_clarification` and `PlanClarificationCard` with upstream direction. Record direct callers and stop for HIGH or CRITICAL risk.

- [ ] **Step 2: Write failing default and opt-out tests**

Add a tool test showing the omitted parameter serializes as true, and a model test showing the omitted card field is true:

```python
@pytest.mark.asyncio
async def test_ask_plan_clarification_enables_custom_response_by_default() -> None:
    response = await ask_plan_clarification(
        prompt="Choose scope",
        kind="single_choice",
        options=["Backend"],
    )

    assert response.metadata["plan_interaction_card"]["allow_custom_response"] is True


def test_plan_clarification_card_enables_custom_response_by_default() -> None:
    card = PlanClarificationCard(
        prompt="Choose scope",
        kind="single_choice",
        options=[{"id": "backend", "label": "Backend"}],
    )

    assert card.allow_custom_response is True
```

Add a second tool test that passes `allow_custom_response=False` and expects false.

- [ ] **Step 3: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/agents/tools/test_planning.py tests/unit/app/plans/test_models.py -q
```

Expected: the new default assertions fail because both defaults are currently false.

- [ ] **Step 4: Implement default and model guidance**

Change only these defaults:

```python
# src/swe/agents/tools/planning.py
allow_custom_response: bool = True,

# src/swe/app/plans/models.py
allow_custom_response: bool = True
```

Extend the tool docstring and Plan Mode clarification instructions with the rule: choice cards already include a system-owned custom-answer path; models must provide only concrete business choices and must not generate an “other”/“自定义” candidate to duplicate it.

- [ ] **Step 5: Verify GREEN**

Re-run the same pytest command. Expected: all tests pass, including explicit `False` behavior.

### Task 2: Preserve legacy metadata compatibility

**Files:**
- Modify: `console/src/pages/Chat/messageMeta.ts:151-280`
- Test: `console/src/pages/Chat/messageMeta.test.ts`

- [ ] **Step 1: Run required impact analysis**

Run GitNexus impact for `extractPlanInteractionCard` with upstream direction. Stop for HIGH or CRITICAL risk.

- [ ] **Step 2: Write a failing legacy-card test**

Add this test:

```ts
it("enables custom response for clarification cards that omit the legacy flag", () => {
  expect(
    extractPlanInteractionCard({
      metadata: {
        plan_interaction_card: {
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "backend", label: "Backend" }],
        },
      },
    }),
  ).toMatchObject({ allow_custom_response: true });
});
```

- [ ] **Step 3: Verify RED**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/messageMeta.test.ts
```

Expected: FAIL because omitted flags currently normalize to false.

- [ ] **Step 4: Implement the normalizer default**

Change the clarification-card normalizer from strict equality to opt-out semantics:

```ts
allow_custom_response: card.allow_custom_response !== false,
```

- [ ] **Step 5: Verify GREEN**

Re-run the focused message-meta test. Expected: all tests pass.

### Task 3: Add field-level custom answer behavior

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx:246-551`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Run required impact analysis**

Run GitNexus impact for `PlanClarificationCard` and `handleSubmit` with upstream direction. Stop for HIGH or CRITICAL risk before editing component logic.

- [ ] **Step 2: Write failing behavior tests**

Add focused tests that demonstrate all payload rules:

```tsx
it("requires text when a required single-choice form field uses custom input", () => {
  render(<PlanClarificationCard data={requiredSingleChoiceForm} />);

  fireEvent.click(screen.getByRole("button", { name: "自定义填写" }));
  expect(screen.getByRole("button", { name: "提交" })).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Scope" }), {
    target: { value: "CLI only" },
  });
  expect(screen.getByRole("button", { name: "提交" })).toBeEnabled();
});

it("submits standard multi-choice ids and field-level custom text independently", async () => {
  const submit = captureSubmitEvents();
  render(<PlanClarificationCard data={multiChoiceForm} />);

  fireEvent.click(screen.getByRole("button", { name: /Lint/ }));
  fireEvent.click(screen.getByRole("button", { name: "自定义填写" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Checks" }), {
    target: { value: "Security scan" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交" }));

  await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
  expect(submit.handler.mock.calls[0][0].detail.biz_params.plan_interaction_response)
    .toMatchObject({
      field_values: { checks: ["lint"] },
      custom_field_values: { checks: "Security scan" },
    });
  submit.cleanup();
});
```

Also assert that a form with `allow_custom_response: false` has no “自定义填写” row and that no global “请输入自定义回复” final step remains.

- [ ] **Step 3: Verify RED**

Run:

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: FAIL because field-level custom state and `custom_field_values` do not exist, and forms still append the global supplemental page.

- [ ] **Step 4: Implement focused state and payload helpers**

Add a `customFieldValues: Record<string, string>` state keyed by field id. Extend `ChoiceRows` with optional custom-row props so only `activeField` choice screens render the system row when `data.allow_custom_response !== false`.

For the active field:

```ts
const customFieldText = activeField
  ? customFieldValues[activeField.id] || ""
  : "";
const hasCustomFieldText = Boolean(customFieldText.trim());
const hasFieldChoice = activeSelectedIds.length > 0;
const currentFieldComplete = activeField
  ? !activeField.required ||
    (activeField.type === "single_choice"
      ? hasFieldChoice || hasCustomFieldText
      : hasFieldChoice || hasCustomFieldText)
  : true;
```

For single-choice custom activation, clear that field’s selected business value. For multi-choice, retain selected business IDs. Do not include the system row in `activeSelectedIds`.

Remove the `isSupplementStep` branch and make form `totalSteps` equal `fields.length`. On submission, build `custom_field_values` from trimmed non-empty `customFieldValues`; add it only when non-empty. Extend the emitted query lines with `field.label: <custom text>` after the corresponding standard selection label.

- [ ] **Step 5: Verify GREEN**

Re-run the focused card test. Expected: all existing and new behavior tests pass.

### Task 4: Make long options readable without expanding the card

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx:279-337`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less:155-272`
- Test: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`

- [ ] **Step 1: Write failing long-option and stylesheet tests**

Add a render assertion that the label carries a full-value title and stylesheet assertions for wrapping and the existing viewport scroll bound:

```tsx
it("keeps complete long option text available within the scrollable viewport", () => {
  const longLabel = "A very long option label that must remain readable";
  render(<PlanClarificationCard data={createLongOptionCard(longLabel)} />);

  expect(screen.getByRole("button", { name: longLabel }))
    .toHaveAttribute("title", longLabel);
  expect(stylesheet).toContain("white-space: normal");
  expect(stylesheet).toContain("overflow-wrap: anywhere");
  expect(stylesheet).toContain("max-height: 244px");
  expect(stylesheet).toContain("overflow-y: auto");
});
```

- [ ] **Step 2: Verify RED**

Run the focused card test. Expected: FAIL because option labels use single-line ellipsis and have no title attribute.

- [ ] **Step 3: Implement wrapping and preserved list scrolling**

Add `title={option.label}` to business option label spans and use `title="自定义填写"` on the system row. In Less, replace the option label truncation rules with:

```less
overflow: visible;
line-height: 20px;
overflow-wrap: anywhere;
text-overflow: clip;
white-space: normal;
word-break: break-word;
```

Keep `.optionRow` at `min-height: 44px` but remove its fixed `flex: 0 0 44px`, so rows may grow for wrapped text. Keep `.choiceOptionsViewport` at `max-height: 244px; overflow-y: auto`.

- [ ] **Step 4: Verify GREEN**

Re-run the focused card test. Expected: all card tests pass.

### Task 5: Full scoped verification

**Files:**
- Verify: all files above

- [ ] **Step 1: Run backend regression tests**

```bash
venv/bin/python -m pytest tests/unit/agents/tools/test_planning.py tests/unit/app/plans/test_models.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Console regression tests**

```bash
cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx src/pages/Chat/messageMeta.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run formatting, lint and production build**

```bash
cd console && pnpm prettier --check src/pages/Chat/components/PlanInteractionCards.tsx src/pages/Chat/components/PlanInteractionCards.module.less src/pages/Chat/components/PlanInteractionCards.test.tsx src/pages/Chat/messageMeta.ts src/pages/Chat/messageMeta.test.ts
cd console && pnpm eslint src/pages/Chat/components/PlanInteractionCards.tsx src/pages/Chat/components/PlanInteractionCards.test.tsx src/pages/Chat/messageMeta.ts src/pages/Chat/messageMeta.test.ts
cd console && pnpm build
```

Expected: formatting and lint pass. If the known unrelated `SystemConfigPage/index.test.tsx` type error still blocks build, report it separately with its exact location.

- [ ] **Step 4: Inspect the scoped diff**

```bash
git diff --check -- src/swe/agents/tools/planning.py src/swe/app/plans/models.py src/swe/agents/react_agent.py tests/unit/agents/tools/test_planning.py tests/unit/app/plans/test_models.py console/src/pages/Chat/messageMeta.ts console/src/pages/Chat/messageMeta.test.ts console/src/pages/Chat/components/PlanInteractionCards.tsx console/src/pages/Chat/components/PlanInteractionCards.module.less console/src/pages/Chat/components/PlanInteractionCards.test.tsx
git diff --stat -- src/swe/agents/tools/planning.py src/swe/app/plans/models.py src/swe/agents/react_agent.py tests/unit/agents/tools/test_planning.py tests/unit/app/plans/test_models.py console/src/pages/Chat/messageMeta.ts console/src/pages/Chat/messageMeta.test.ts console/src/pages/Chat/components/PlanInteractionCards.tsx console/src/pages/Chat/components/PlanInteractionCards.module.less console/src/pages/Chat/components/PlanInteractionCards.test.tsx
```

Expected: only files listed in this plan, excluding pre-existing user changes.

- [ ] **Step 5: Run GitNexus change detection**

Run `detect_changes({ scope: "unstaged", repo: "CoPaw" })`. Review the changed symbols and affected flows, treating any unrelated existing worktree changes as out of scope; report HIGH or CRITICAL results before committing.
