---
title: Scheduler Feedback Safety Supplement
status: active
created: 2026-07-02
related:
  - docs/plans/2026-07-01-001-independent-cron-scheduling-service-design.md
  - docs/adr/0010-independent-cron-scheduling-service-owns-batch-dispatch.md
---

# Scheduler Feedback Safety Supplement

Scheduler callbacks include `dispatch_attempt` in addition to
`dispatch_intent_id` and `dispatch_batch_id`.

Scheduler uses `(dispatch_intent_id, dispatch_batch_id, dispatch_attempt)` as
the execution-feedback idempotency key. If SWE retries the feedback request,
Scheduler reuses the existing execution row instead of inserting a duplicate.
The full dispatch metadata is still retained in `swe_cron_executions.meta`,
but the same three identity values are also written into
`dispatch_intent_id`, `dispatch_batch_id`, and `dispatch_attempt` columns with
the `idx_cron_execution_dispatch` index. Feedback de-duplication must use
those indexed columns instead of parsing JSON from `meta`.

Scheduler also validates the attempt count before completing a durable intent.
A late stale callback from attempt 1 cannot complete the same intent after it
has already been reclaimed and dispatched as attempt 2.

This keeps immediate refill safe: a completed child can trigger the next
dispatch immediately, while worker-capacity adjustment remains interval-gated
and independent.
