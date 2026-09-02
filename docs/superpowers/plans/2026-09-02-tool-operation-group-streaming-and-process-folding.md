---
title: Improve streaming tool operation groups
type: fix
status: active
date: 2026-09-02
origin: docs/brainstorms/2026-08-27-tool-call-grouping-requirements.md
---

# Improve streaming tool operation groups

## Summary

Extend the existing Console-only operation-group presentation so a group appears on its first live tool call, preserves interleaved reasoning and action-oriented tool labels, and moves into the existing execution-process disclosure after the response completes.

---

## Requirements

- R22. Render an open operation group immediately from its first live grouped tool call.
- R23. Prefer the call action summary over the terminal result summary for group step labels.
- R24. Preserve reasoning messages inside an open group in stream order.
- R25. Move completed operation groups into ProcessDisclosure while keeping live groups directly visible.

**Origin actors:** A1 Console user, A3 runtime and Console
**Origin flows:** F1 create/update group, F2 collapse/expand
**Origin acceptance examples:** AE12, AE13, AE14, AE15

---

## Scope Boundaries

- Do not change backend operation-group fields, Tool Guard semantics, persistence, or approval replay.
- Do not expose raw tool arguments or outputs.
- Do not infer groups for events without an explicit operation-group declaration.
- Do not redesign ProcessDisclosure or the broader Conversation Workspace.

---

## Context & Research

### Relevant Code and Patterns

- `operationGrouping.ts` currently flushes a trailing open group, but treats reasoning as a hard boundary and prefers terminal `output_summary` for ordinary tools.
- `OperationGroup.tsx` owns the safe, default-collapsed group UI and fixed tool-step presentation.
- `Card.tsx` currently routes every group to `direct`, explicitly excluding groups from ProcessDisclosure.
- `Reasoning.tsx` is the existing rendering contract for reasoning content and should be reused inside a group.

---

## Key Technical Decisions

- Keep grouping as a pure projection over the current merged message list; an unfinished group is a valid renderable result.
- Treat reasoning after a grouped tool as part of the open group until user-facing text, an ungrouped tool, or a new group closes it.
- Derive group status and tool counts from tool messages only; reasoning participates in ordering and process-step counts but not tool status aggregation.
- Reuse the existing Reasoning component within OperationGroup and keep raw Tool cards excluded.
- Route grouped items into ProcessDisclosure only after the existing response-completion gate succeeds.

---

## Implementation Units

### U1. Extend grouping semantics and labels

**Goal:** Preserve reasoning in an open group, render unfinished groups, and prefer action summaries.

**Requirements:** R22, R23, R24; AE12, AE13, AE14

**Dependencies:** None

**Files:**
- `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/operationGrouping.ts`
- `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/operationGrouping.test.ts`

**Execution note:** Add failing tests before changing projection logic.

**Test scenarios:**
- A single running grouped tool produces a group immediately.
- Call summary wins when both call and output summaries exist.
- Tool, reasoning, and same-group tool remain ordered in one group.
- User-facing text, ungrouped tools and a new group remain boundaries.
- Reasoning does not alter aggregate tool status.

### U2. Render reasoning inside operation groups

**Goal:** Reuse the established reasoning presentation inside expanded group details.

**Requirements:** R24; AE14

**Dependencies:** U1

**Files:**
- `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/OperationGroup.tsx`
- `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/OperationGroup.test.tsx`
- `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/style.ts`

**Test scenarios:**
- Reasoning appears between the correct two tool steps after expansion.
- Collapsed groups hide reasoning.
- Reasoning never exposes raw tool details or changes the group status icon.

### U3. Fold completed groups into execution process

**Goal:** Keep live groups direct and move completed groups under ProcessDisclosure.

**Requirements:** R22, R25; AE12, AE15

**Dependencies:** U1, U2

**Files:**
- `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/Card.tsx`
- `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/Card.test.tsx`

**Test scenarios:**
- A generating response displays the first grouped tool directly without ProcessDisclosure.
- A completed response with final text places the whole group inside ProcessDisclosure.
- Process counts include grouped reasoning and tools once; tool-call counts include tools only.
- Failed grouped tools contribute to the ProcessDisclosure failure count.

---

## Verification Strategy

- Run the three focused Response test files with Vitest.
- Run Console TypeScript typecheck, Prettier check and ESLint for changed files.
- Attempt the Console build and one browser screenshot pass; report unrelated baseline blockers without changing them.
- Run `git diff --check` and GitNexus change detection before any commit.

---

## Sources & References

- `docs/brainstorms/2026-08-27-tool-call-grouping-requirements.md`
- `console/DESIGN.md`
- `docs/adr/0003-tool-call-status-is-rebuilt-for-presentation.md`

---

## Follow-up: preserve Tool Guard status across the live adapter

- Add a regression test for the complete `Msg -> AgentScope live adapter -> Runner stream boundary` path and prove that pending approval is not projected as execution failure.
- Copy only trusted Tool Guard governance markers into internal message metadata keyed by tool call ID before the adapter rebuilds tool-result blocks.
- Consume and remove that private metadata at the Runner stream boundary, then reuse the existing `tool_governance` projection for pending, rejected and blocked states.
- Keep ordinary tool output untrusted: `error_type` text alone must not create a governance status.
