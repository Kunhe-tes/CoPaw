---
title: Align W+ SOP workspace with the Console design baseline
type: refactor
status: complete
date: 2026-07-31
origin: AGENTS.md
---

# Align W+ SOP workspace with the Console design baseline

## Summary

Refine the existing W+ SOP workspace into a compact, white-first Conversation
Workspace surface using the established blue emphasis, stable operational
states, and responsive behavior without changing any workflow contract.

## Requirements

- R1. Use the Conversation Workspace emphasis color `#3769FC` and the existing
  Console semantic variables instead of the page-local green visual language.
- R2. Keep the current task, current state, progress, and primary operation
  visible in the first viewport with medium-high desktop density.
- R3. Remove decorative gradients, heavy shadows, oversized containers, and
  avoid nested-card presentation where a border or subtle surface is enough.
- R4. Preserve labels, focus visibility, non-color status cues, reduced-motion
  behavior, long-text resilience, and narrow embedded-container usability.
- R5. Preserve every existing API call, route, ownership check, SSE behavior,
  state transition, input draft, action outcome, and debug-stream contract.

## Scope Boundaries

- Do not change backend code, API types, request payloads, route paths, or
  session-state semantics.
- Do not change the global Console design tokens or restyle unrelated Chat and
  management surfaces.
- Do not redesign the W+ Chat entry card or sticky active bar in this change.
- Do not introduce a new design system, external font, animation dependency, or
  persistent debug-stream behavior.

## Context & Research

### Relevant Code and Patterns

- `AGENTS.md`: Console UI Design Principles and required visual verification
  sizes.
- `console/DESIGN.md`: white-first baseline, Conversation Workspace priority,
  spacing, typography, state, accessibility, and embedded behavior.
- `console/src/config/consoleDesignTokens.ts`: existing base, management, and
  conversation semantic CSS variables.
- `console/src/pages/WPlusSopWorkspace/index.tsx`: current state-dependent W+
  interaction surface.
- `console/src/pages/WPlusSopWorkspace/index.module.less`: current green
  gradient and raised-card presentation.
- `console/src/pages/WPlusSopWorkspace/index.test.tsx`: existing workflow,
  recovery, SSE, and debug-trace characterization coverage.

### Institutional Learnings

- The W+ workspace is a specialized view of the owning Chat and remains the
  sole answer-submission surface.
- Persisted Session state is authoritative; visual changes must not infer or
  replace workflow state from frontend-only presentation.
- Current local modifications in Chat and backend ownership handling are
  unrelated and must remain untouched.

## Key Technical Decisions

- Keep visual changes page-scoped and consume shared CSS variables with literal
  fallbacks, so embedded hosts retain a correct surface even before token
  initialization.
- Retain the existing DOM interaction controls and state branches; add only
  semantic status/progress structure needed for accessible, task-first display.
- Replace centered generation “hero” treatment with a compact operational
  status region while keeping the debug trace discoverable by hover, focus, and
  click.
- Use borders and subtle surfaces for hierarchy, reserving shadow for the debug
  popover overlay.

## Implementation Units

### U1. Characterize the visible operational shell

**Goal:** Protect the task-first and accessibility structure before restyling.

**Requirements:** R2, R4, R5

**Dependencies:** None

**Files:**

- Modify: `console/src/pages/WPlusSopWorkspace/index.test.tsx`
- Modify: `console/src/pages/WPlusSopWorkspace/index.tsx`

**Approach:**

- Add focused assertions for the named workspace header, live generation
  status, labelled progress, and loading explanation.
- Add only the semantic markup/classes required to satisfy those assertions;
  retain all existing event handlers and state branches.

**Execution note:** Start with a failing focused component test, then implement
the smallest semantic change.

**Test scenarios:**

- Loading: unresolved Session request renders a named loading state rather than
  an unexplained skeleton.
- Generating: a generating Session exposes an accessible live status and a
  labelled progress indicator while retaining the debug-stream control.
- Ready: the page exposes the Session title and current state without changing
  any command behavior.

**Verification:**

- Existing W+ component tests and the new structural assertions pass.

### U2. Align the page-scoped visual system and responsive layout

**Goal:** Apply the new Console visual baseline across ready, generating,
decision, loading, empty, and error states.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** U1

**Files:**

- Modify: `console/src/pages/WPlusSopWorkspace/index.module.less`
- Modify: `console/src/pages/WPlusSopWorkspace/index.tsx`

**Approach:**

- Map page variables to the shared Console semantic variables and Conversation
  primary color.
- Compress the header and progress regions, reduce card elevation and radii,
  use open white canvas grouping, and keep the primary operation visible.
- Make the evidence rail sticky only where width permits. Below 760px, remove
  the desktop rail from layout and expose the same evidence through a named,
  closable right-side drawer.
- Keep the stage progress queue compact on phones by switching it to a
  horizontally scrollable sequence instead of stacking every stage vertically.
- Harden long mixed-language content, tables, action wrapping, focus styles,
  reduced motion, and no-horizontal-overflow behavior.

**Test scenarios:**

- Test expectation: none for pure CSS rules; behavioral coverage remains in U1
  and existing component tests.

**Verification:**

- Visual inspection at `1280x720`, `1440x900`, and `1920x1080`.
- Embedded or narrow-shell inspection with no horizontal page overflow,
  including the evidence-drawer entry and close path.
- Hover, focus, loading, generating, failure, and actionable ready states remain
  visually distinct without relying only on color.
- Frontend lint, formatting, targeted tests, and build succeed.

## System-Wide Impact

- **Interaction graph:** unchanged; the route still renders the same component
  and calls the same W+ API adapter and SSE subscription.
- **Error propagation:** unchanged; 404 stays non-leaking and other failures
  keep their retry path.
- **State lifecycle risks:** visual restructuring must not remount controls or
  clear drafts during Session updates.
- **API surface parity:** no request or response contracts change.
- **Integration coverage:** browser inspection verifies the real compiled CSS
  and shell behavior that component tests cannot prove.
- **Unchanged invariants:** the owning Chat remains the source entry and W+
  remains the sole answer/feedback submission surface.

## Risks & Dependencies

| Risk                                              | Mitigation                                                                                      |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| CSS changes hide actions below the first viewport | Compress shell regions and inspect the required desktop sizes.                                  |
| Long stage names or result cells create overflow  | Preserve `min-width: 0`, intentional wrapping, and table-local scrolling.                       |
| New status structure alters behavior              | Keep handlers and conditions unchanged; add component assertions before styling.                |
| Global theme leakage                              | Keep all new rules inside the existing CSS module and consume, rather than edit, shared tokens. |

## Sources & References

- `AGENTS.md`
- `console/DESIGN.md`
- `docs/adr/0013-wplus-sop-uses-persisted-session-and-structured-envelope.md`
- `docs/superpowers/specs/2026-07-17-wplus-sop-workspace-design.md`
- `docs/superpowers/plans/2026-07-28-wplus-sop-workspace-v1.md`
