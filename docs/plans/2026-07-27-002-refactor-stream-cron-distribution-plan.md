---
title: "refactor: Stream scheduled firing distribution aggregation"
type: refactor
status: completed
date: 2026-07-27
origin: docs/plans/2026-07-27-001-feat-cron-trigger-distribution-plan.md
---

# refactor: Stream scheduled firing distribution aggregation

## Summary

Change only the Monitor aggregate calculation so each planned firing is counted directly into its time bucket. Keep the aggregate/detail HTTP contracts, current cron semantics, diagnostics, revision behavior, and detail ordering unchanged.

---

## Requirements

- R1. The aggregate endpoint must not materialize or sort the full occurrence list.
- R2. Aggregate bucket, Text, Agent, total, eligible-job, diagnostic, revision, and calculation-time fields must remain behaviorally compatible.
- R3. A definition that fails during cron iteration must not leave partial counts in the response.
- R4. The 100,000-occurrence calculation limit must retain its fail-without-partial-response behavior.
- R5. The detail endpoint must retain stable `(scheduled_at, job_id)` ordering and on-demand occurrence materialization.

---

## Scope Boundaries

- No frontend, route, response-model, database, or migration changes.
- No cache, background task, `swe_async_tasks`, or `swe_async_task_items` integration.
- No change to source isolation, timezone/DST behavior, broadcast-child exclusion, or Scheduled Firing Count semantics.

---

## Key Technical Decisions

- Extract shared definition validation and schedule-time iteration so aggregate and detail paths cannot drift.
- Aggregate into pre-created response buckets, but keep a per-definition temporary bucket map and commit it only after that definition finishes successfully.
- Count accepted firings separately from response objects so the calculation limit remains independent of materialization.
- Keep the existing materialized and sorted detail path because pagination requires deterministic global ordering.

---

## Implementation Units

### U1. Share schedule validation and iteration

**Goal:** Centralize eligibility, diagnostics, timezone fallback, and cron iteration behavior.

**Requirements:** R2, R3, R4, R5

**Dependencies:** None

**Files:**
- Modify: `monitor/src/monitor/app/services/cron/query_service.py`
- Test: `monitor/tests/test_cron_schedule_distribution.py`

**Approach:**
- Introduce a small prepared-definition value object.
- Extract one helper that validates a row and updates diagnostics.
- Extract one iterator that yields UTC firing instants with the existing `[start, end)` behavior.
- Refactor the detail occurrence generator to use both helpers without changing its result or sort order.

**Execution note:** Add characterization and regression tests before refactoring.

**Test scenarios:**
- Integration: aggregate and detail counts reconcile for valid Text/Agent definitions.
- Error path: invalid type, metadata, cron, and timezone diagnostics remain unchanged.
- Edge case: range boundaries and timezone/DST calculations remain unchanged.

**Verification:**
- Existing schedule-distribution tests pass before the aggregate path is switched.

### U2. Stream aggregate firings into buckets

**Goal:** Remove aggregate full-list allocation and sorting.

**Requirements:** R1, R2, R3, R4

**Dependencies:** U1

**Files:**
- Modify: `monitor/src/monitor/app/services/cron/query_service.py`
- Test: `monitor/tests/test_cron_schedule_distribution.py`

**Approach:**
- Load and revise the same source-scoped definitions as today.
- Build the requested buckets first.
- For each eligible definition, accumulate firings in a definition-local bucket map, then commit it to the response buckets only after successful iteration.
- Enforce the global occurrence limit while iterating.
- Prove the aggregate path no longer calls the materialized occurrence generator.

**Execution note:** Start with a failing test that replaces the materialized generator with an exception.

**Test scenarios:**
- Happy path: aggregate succeeds even when the materialized detail generator is unavailable.
- Regression: every aggregate field matches the detail-derived firing set.
- Error path: a mid-definition iterator failure contributes diagnostics but no partial bucket counts.
- Error path: the occurrence cap fails the whole request.

**Verification:**
- Targeted Monitor tests pass and representative dense schedules show lower elapsed time and bounded aggregation memory.

---

## System-Wide Impact

- **Interaction graph:** Only `QueryService.get_schedule_distribution` changes its internal calculation path; the detail endpoint keeps `_calculate_schedule_occurrences`.
- **Error propagation:** Validation and limit errors remain request failures; definition-level cron errors remain diagnostics.
- **State lifecycle risks:** There are no writes. Definition revision and calculation timestamp are still computed from the same loaded snapshot.
- **API surface parity:** Both Monitor endpoints and the console client remain unchanged.
- **Unchanged invariants:** Source scoping, `[start, end)` ranges, cron/timezone semantics, Text/Agent classification, and stable detail ordering remain intact.

---

## Risks & Dependencies

| Risk | Mitigation |
|---|---|
| Shared-helper refactor changes diagnostics or eligibility | Characterization tests cover every exclusion and fallback branch |
| Cron iteration fails after yielding some times | Commit per-definition counters only after successful completion |
| Aggregate and detail paths drift later | Both consume the same preparation and UTC-time iterator helpers |
| Limit semantics change at the boundary | Preserve the existing pre-append limit check and add exact-boundary regression coverage |

---

## Sources & References

- `docs/plans/2026-07-27-001-feat-cron-trigger-distribution-plan.md`
- `CONTEXT.md`
- `monitor/src/monitor/app/services/cron/query_service.py`
- `monitor/tests/test_cron_schedule_distribution.py`
