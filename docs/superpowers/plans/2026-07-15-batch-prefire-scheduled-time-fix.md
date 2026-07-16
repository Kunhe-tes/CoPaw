---
title: Fix batch pre-fire scheduled time inference
type: fix
status: complete
date: 2026-07-15
---

# Fix batch pre-fire scheduled time inference

## Summary

Correct Scheduler's fallback inference for batch callbacks that arrive before the parent cron time without an explicit trigger timestamp. The batch must use the upcoming parent fire time when the callback is inside the configured pre-fire window, while delayed callbacks must continue using the most recent due time.

## Requirements

- R1. Preserve explicit `scheduled_fire_at` and explicit trigger-time-plus-offset behavior.
- R2. For a positive batch dispatch offset, map a callback inside the pre-fire window to the next parent cron occurrence.
- R3. Outside that pre-fire window, keep the existing previous-due fallback so delayed or retried callbacks do not create a future batch.
- R4. Propagate the corrected time to the deterministic batch identity and `parent_scheduled_fire_at` notification metadata.

## Scope Boundaries

- Do not change the external callback API contract or require the external scheduler to send new fields.
- Do not change notification claiming or frontend time formatting.
- Do not alter non-batch cron scheduling behavior.

## Key Technical Decisions

- Infer the upcoming fire only when it is no farther away than the positive batch offset. This ties the fallback to the configured pre-fire contract and avoids converting late callbacks into the next day's batch.
- Calculate the upcoming occurrence from the parent cron and timezone instead of adding the offset to receipt time, so callback latency does not shift the planned fire time.

## Implementation Units

### U1. Characterize pre-fire and delayed callbacks

**Goal:** Reproduce the cross-day failure and lock down the delayed-callback invariant.

**Requirements:** R1, R2, R3, R4

**Files:**
- Test: `tests/unit/scheduler/test_cron_scheduling_service.py`

**Execution note:** Test-first.

**Test scenarios:**
- Happy path: a Beijing callback at 16:00:01 for a 20:00 parent cron with a 240-minute offset produces the same-day 20:00 scheduled fire.
- Edge case: a callback after the 20:00 parent fire keeps the same-day 20:00 previous-due occurrence rather than selecting the next day.
- Regression: explicit trigger timestamp plus offset remains unchanged.

**Verification:** Persisted batch time and execution payload use the expected parent fire time.

### U2. Select the correct cron occurrence

**Goal:** Add the minimal Scheduler fallback needed to distinguish pre-fire callbacks from delayed callbacks.

**Requirements:** R2, R3

**Dependencies:** U1

**Files:**
- Modify: `scheduler/src/scheduler/app/services/cron/scheduling_service.py`

**Approach:**
- Retain request-provided times as the first priority.
- Compute both adjacent parent cron occurrences only for fallback inference.
- Choose the upcoming occurrence only when a positive batch offset contains it; otherwise choose the previous occurrence.

**Patterns to follow:**
- Existing timezone-aware `_previous_due_fire_at` helper and callback normalization.

**Test scenarios:**
- Integration: parent callback persistence and execution intent metadata both receive the selected occurrence.
- Error path: invalid cron expressions continue falling back safely to callback receipt time.

**Verification:** Scheduler callback tests pass without changing the request schema.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| A delayed callback could be associated with a future batch | Limit next-occurrence selection to the configured pre-fire window. |
| Timezone or midnight boundaries could regress | Compute cron occurrences in the parent timezone and normalize to UTC, matching existing behavior. |

## Sources & References

- `docs/superpowers/specs/2026-07-02-batch-dispatch-rollout-rollback-design.md`
- `docs/plans/2026-07-02-004-batch-dispatch-scheduler-implementation-report.md`
- `scheduler/src/scheduler/app/services/cron/scheduling_service.py`
