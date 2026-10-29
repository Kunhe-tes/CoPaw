# Archived History Assembly Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or inline execution. Track each task below and verify failures before implementation.

**Goal:** Keep every archived runtime fragment, assemble continuous loaded responses across archive pages/boundaries, and pair tools independent of input/output order.

**Architecture:** Keep source identity in original_id and use stable distinct runtime fragment IDs. Normalize legacy repeated IDs at the frontend boundary. Merge loaded historical response fragments while retaining inline compaction markers, explicit turn barriers, and the newest bubble identity for scrolling.

**Tech Stack:** Python/pytest; TypeScript/React/Vitest.

## Task 1 — Tool pairing

- [x] Add `Response/ToolMessageMerge.test.ts`: reversed order, same-name distinct calls, repeated input/output, immutable source objects, missing side.
- [x] Run that file and confirm reversed order fails.
- [x] Update `ToolMessageMerge.ts` to associate by explicit call ID in either order, preserving the output terminal metadata and a stable first occurrence position.
- [x] Re-run targeted tests and existing Response tests.

## Task 2 — Fragment identity

- [x] Add backend coverage in `tests/unit/app/test_chat_compaction_history_api.py` for thinking + multiple calls/results under one Msg; assert unique stable IDs and unchanged original_id.
- [x] Run pytest and confirm duplicate IDs fail.
- [x] Give historical fragments distinct stable display IDs in `src/swe/app/runner/api.py` while retaining original IDs in metadata and leaving live SSE unchanged.
- [x] Run archive, timestamp, answer-turn and sharing regressions.

## Task 3 — Legacy identity and history assembly

- [x] Add failing tests in `console/src/pages/Chat/sessionApi/historyAssembly.test.ts` for repeated legacy IDs, same-turn cross-page merging, boundaries retained inline, explicit users and standalone outputs as barriers, task execution boundaries and stable IDs.
- [x] Add a focused `historyAssembly.ts` module for legacy fragment identity, archive-response merging and merged-anchor lookup; keep card-derived raw output, not a second unbounded raw history cache.
- [x] Call normalization at conversion and before archive duplicate filtering, and merge inside the React functional prepend update.
- [x] Render inline compaction boundary runtime entries using the existing separator component. Keep markers out of tool counters and final answer detection.
- [x] Preserve internal reading anchors when merged cards reflow; retain existing session generation lifecycle.
- [x] Run sessionApi/MessageList/Response regression suites.

## Task 4 — Integration and delivery

- [x] Add MessageList integration coverage for same-source fragments and repeated loads across pages using real assembly helpers.
- [x] Run targeted pytest, frontend tests, ESLint/Prettier and production build. Existing `types.tsx` `any` lint errors are unrelated; Vite emitted its existing chunk warnings.
- [x] Verify scroll-anchor behavior through MessageList integration tests.
- [x] Update the approved spec and playbook with actual changes, verification results and remaining data limitations. Leave existing unrelated workspace changes intact.

Browser QA note: the local browser access host was unavailable in this environment, so
cross-page loading was verified by the MessageList integration tests rather than a live browser.
