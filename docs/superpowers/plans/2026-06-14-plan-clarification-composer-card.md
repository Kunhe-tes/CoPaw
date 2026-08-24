# Planning Clarification Composer Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the normal chat composer with an interactive Planning Clarification Card while a latest clarification is active, then restore the preserved composer after submission or dismissal.

**Architecture:** Keep the existing `sender.beforeUI` integration and normal composer mounted so draft text and attachments remain intact. The active clarification component owns submission/dismissal persistence, keyboard navigation, and field paging; Chat-page-scoped CSS hides the ordinary composer only while the active-card marker exists.

**Tech Stack:** React 18, TypeScript, CSS Modules/Less, Vitest, Testing Library.

---

### Task 1: Active-card lifecycle and composer replacement

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Modify: `console/src/pages/Chat/index.module.less`

- [ ] Write failing tests for dismissal persistence and latest-card supersession.
- [ ] Run focused tests and verify the new assertions fail.
- [ ] Implement active-card marker and session-scoped dismissal persistence.
- [ ] Add Chat-page-scoped CSS that hides the normal composer while preserving its mounted state.
- [ ] Run focused tests and verify they pass.

### Task 2: Choice-card keyboard interaction

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less`

- [ ] Write failing tests for focus-only initial state, single-choice submission, multi-choice toggling, and mutually exclusive custom response.
- [ ] Run focused tests and verify the new assertions fail.
- [ ] Implement numbered option rows, focus/selection separation, internal scrolling, and keyboard controls.
- [ ] Run focused tests and verify they pass.

### Task 3: Paged form and text interaction

**Files:**
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.tsx`
- Modify: `console/src/pages/Chat/components/PlanInteractionCards.module.less`

- [ ] Write failing tests for field-per-page navigation, Enter/Shift+Enter behavior, and Escape back/dismiss behavior.
- [ ] Run focused tests and verify the new assertions fail.
- [ ] Implement paged field rendering and final optional supplemental-response page.
- [ ] Run focused tests and verify they pass.

### Task 4: Verification

**Files:**
- Modify: `CONTEXT.md`

- [ ] Sync resolved dismissal and custom multi-choice language into `CONTEXT.md`.
- [ ] Run Plan Interaction card tests.
- [ ] Run Chat Input tests to verify composer draft/attachment behavior remains intact.
- [ ] Run Console typecheck/build.
- [ ] Run GitNexus change detection and inspect affected scope.
