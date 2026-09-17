## 1. Pre-implementation safety and test baselines

- [x] 1.1 Run GitNexus upstream impact analysis for every backend and frontend symbol that will be modified (`FeaturedCaseStore` queue methods, `FeaturedCaseService`, featured-case route handlers, `FeaturedCasesPage`, `createCaseColumns`, and featured-case API/hooks); record blast radius and stop for user confirmation on any HIGH or CRITICAL result.
- [x] 1.2 Run the current focused backend and frontend featured-case tests to capture a clean baseline before product-code edits.
- [x] 1.3 Inspect the current management page in normal and `hideMenu=true` contexts and record the existing table, pagination, and BBK context behavior that must be preserved outside the approved changes.

## 2. Backend queue model and transactional store

- [x] 2.1 Add canonical featured-case BBK scope helpers that treat missing, blank, and `100` as head office and produce exact-scope SQL predicates without changing runtime aggregation semantics.
- [x] 2.2 Add reorder request and response models with positive-integer validation and a response containing `case_id`, final `sort_order`, and exact-scope `total`.
- [x] 2.3 Implement an explicitly acquired single-connection transaction helper/path for locking one indexed featured-case queue, including rollback on any error and stable `sort_order ASC, id ASC` ordering.
- [x] 2.4 Implement exact-scope queue normalization, target removal/insertion with maximum-position clamping, batched `1..N` persistence, and lazy canonicalization of legacy head-office BBK values.
- [x] 2.5 Change case creation to lock and normalize its exact queue, append at `N + 1`, and return the persisted row including its database ID.
- [x] 2.6 Change case deletion to verify the writable source/BBK scope, delete atomically, and compact the surviving exact queue.
- [x] 2.7 Prevent the generic content-update path from directly changing `sort_order` and make update lookup enforce the caller's writable source/BBK scope.

## 3. Backend routes, authorization, and query semantics

- [x] 3.1 Change the management list query to return only the explicitly requested logical BBK scope with exact-scope total and deterministic `sort_order ASC, id ASC` pagination.
- [x] 3.2 Preserve and test runtime display composition: head office returns active head-office cases only; a branch returns active exact-branch cases followed by active head-office cases.
- [x] 3.3 Add `PUT /featured-cases/admin/cases/{case_id}/order` and connect it to the transactional reorder service.
- [x] 3.4 Enforce `X-Source-Id` and normalized `X-Bbk-Id` ownership on create, content update, reorder, and delete, while allowing branch contexts read-only management queries for the head-office scope.
- [x] 3.5 Return non-revealing not-found/forbidden errors for cross-source, cross-branch, and branch-to-head-office mutation attempts without changing either queue.

## 4. Backend verification

- [x] 4.1 Add store tests for moving up, moving down, unchanged targets, maximum clamping, active/inactive participation, duplicate/gap repair, head-office value canonicalization, create append, delete compaction, and database rollback.
- [x] 4.2 Add service/router tests for exact-scope pagination, dedicated reorder response shape, invalid input rejection, persisted create IDs, and source/BBK mutation authorization.
- [x] 4.3 Add concurrency-oriented tests proving same-queue mutations serialize against the latest order and different branch queues remain isolated.
- [x] 4.4 Add runtime query regression tests for head-office-only display and branch-first plus head-office fallback ordering.

## 5. Frontend API and scope state

- [x] 5.1 Add reorder request/response TypeScript types and a dedicated featured-case API method; update management list calls to always send the selected exact BBK scope.
- [x] 5.2 Extend the featured-case hook with exact-scope loading and reorder state while preserving recoverable errors instead of swallowing them.
- [x] 5.3 Add management scope navigation: non-head-office contexts show independent "本机构案例" and read-only "总行案例" views, while head-office contexts show only the head-office scope.
- [x] 5.4 Keep pagination state and totals isolated per management scope so changing tabs does not mix positions or counts.
- [x] 5.5 Hide create, content-edit, order-edit, and delete actions in the read-only head-office view and display a concise explanation of the restriction.

## 6. Frontend inline ordering interaction

- [x] 6.1 Replace the static order cell on writable rows with the current number plus an always-discoverable accessible edit action using the established Ant Design icon family.
- [x] 6.2 Implement a single-row inline `InputNumber` editor with automatic focus/selection, integer validation, confirm, cancel, Enter, Escape, and guarded blur submission without row-height movement or duplicate requests.
- [x] 6.3 Reject empty, non-numeric, fractional, zero, and negative values locally; permit above-maximum input and rely on the server response for final clamping.
- [x] 6.4 Disable competing sort edits while saving; on failure retain the attempted value and edit mode with inline/message feedback and retry or Escape cancellation.
- [x] 6.5 On success compute the destination page from the server-confirmed position, reload that exact-scope page, show success feedback, and briefly identify the moved row in a reduced-motion-safe way.
- [x] 6.6 After deletion, load a valid remaining page for the same scope and display the server-compacted sequence.

## 7. Frontend tests and visual hardening

- [x] 7.1 Add component tests for scope tabs, head-office read-only controls, head-office-only context, exact-scope requests, and independent pagination.
- [x] 7.2 Add interaction tests for edit entry, prefilled selection, valid Enter/confirm/blur commits, Escape cancellation, unchanged no-op, validation failures, duplicate-submit prevention, retry after failure, maximum clamping response, cross-page relocation, and moved-row feedback.
- [x] 7.3 Add integration coverage showing that management reordering changes the relative order consumed by chat without changing branch-first plus head-office fallback grouping.
- [x] 7.4 Keep the changed page aligned with `console/DESIGN.md`: stable dense table rows, visible keyboard focus, accessible icon labels, no hover-only primary operation, and complete loading/error/disabled/read-only states.

## 8. Final verification and handoff

- [x] 8.1 Run focused Python tests for the featured-case store, service, and router, then run the relevant broader backend test target.
- [x] 8.2 Run frontend unit tests, lint, type checking, and production build for the Console.
- [x] 8.3 Verify the management page at `1280x720`, `1440x900`, and `1920x1080`, plus `hideMenu=true`, covering writable and read-only scopes, inline edit states, long labels, pagination, and failure recovery.
- [x] 8.4 Verify representative chat behavior for head-office and branch contexts after reorder, disable, create, and delete operations.
- [x] 8.5 Run GitNexus `detect_changes` against `main`, confirm only expected symbols and execution flows are affected, and resolve or report any unexpected blast radius.
- [x] 8.6 Run OpenSpec validation/status checks, update all completed task checkboxes, and report any verification that could not be completed.

## 9. Review hardening

- [x] 9.1 Keep case creation result loading inside the mutation transaction and roll back when it fails.
- [x] 9.2 Isolate frontend list data, totals, and loading state by exact scope and ignore stale same-scope responses.
- [x] 9.3 Distinguish reorder persistence failures from post-save list refresh failures while preserving the attempted input.
- [x] 9.4 Replace the sequential concurrency check with overlapping transaction tasks that verify queue serialization.
- [x] 9.5 Re-run focused backend/frontend tests, lint/type checks, OpenSpec validation, and GitNexus change detection.
