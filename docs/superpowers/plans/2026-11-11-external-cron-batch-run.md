# External Cron Batch Run Implementation Plan

**Goal**

Allow an authorized external caller to run a managed batch by posting only its parent `jobId`.

**Architecture**

Add `POST /api/scheduler/external/cron/batch/run` beside the external Cron query. Resolve the parent with the existing gateway identity and task authorization. Reuse the Scheduler transaction that records the batch receipt, member snapshots, priority, and queue entries. Manual triggers use receipt time and bypass the automatic workday filter. They honor batch mode, pause, and executable date ranges.

## Implementation

- [x] Add HTTP tests in `tests/unit/scheduler/test_external_cron_batch_run.py` for parent and child queueing, missing or unauthorized identity, and blocked batches. Verify the new route returns 404 before implementation.
- [x] In `external_cron.py`, add the one-field request model, existing identity and runtime dependencies, and 202/400/404/409/422/503 mapping. In `managed/scheduling.py`, share transactional admission and recording with the platform callbacks. Manual receipts identify the request as manual and contain no platform operation reference.
- [x] Document request, authorization, response, and repeat-submission semantics in `docs/integrations/zhituo-scheduler-cron-api-v1.md`. Record the domain term in `scheduler/CONTEXT.md`.
- [x] Verify the new route through the Scheduler-to-SWE HTTP chain. Run the focused tests and Scheduler unit suite, compare failures against `HEAD`, and check the diff. Leave the changes available for user review in the working tree.

## Follow-up for active batches

- [x] Verify queued, running and unsettled members block a second external trigger. Cover concurrent external calls and a batch already accepted by the platform callback.
- [x] Check for an unfinished batch under the existing parent task lock. Return HTTP 409 with its `batch_id` and keep platform callback admission independent.
- [x] Verify a new external request succeeds after the previous batch settles. Update the API contract and run the focused HTTP and Scheduler regression tests.
