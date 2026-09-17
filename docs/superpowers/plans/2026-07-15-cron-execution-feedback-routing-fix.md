# Cron Execution Feedback Routing Fix

## Scope

- Keep Scheduler as the execution-feedback target only for dispatch-managed
  executions with a complete durable identity.
- Route B3-only and other non-dispatch cron executions to Monitor.
- Do not change Scheduler or Monitor persistence behavior.

## Acceptance Criteria

1. `cron_dispatch` metadata routes to Scheduler only when it contains a
   positive `intent_id`, a non-empty `batch_id`, and a positive
   `dispatch_attempt`.
2. B3-only metadata nested under `cron_dispatch` routes to Monitor.
3. Within the serialized execution metadata evaluated by the routing
   predicate, missing, malformed, zero, or negative dispatch identity values
   route to Monitor.
4. Valid dispatch-managed execution feedback continues to use Scheduler and
   retains its existing retry behavior.

## Boundary

This fix does not change normalization of authenticated Scheduler callback
parameters in `src/swe/app/routers/internal.py`. That compatibility layer
currently defaults a missing callback `dispatch_attempt` to `1` and normalizes
numeric inputs before execution metadata is built. Tightening that external
callback contract is a separate change; this fix only prevents B3-only or
otherwise incomplete serialized execution metadata from selecting Scheduler.

## TDD Steps

1. Add a focused unit test in
   `tests/unit/app/test_monitor_sync_client.py` proving B3-only metadata calls
   the Monitor execution path and never calls the Scheduler execution path.
2. Run the new test and confirm it fails against the current dictionary-only
   predicate.
3. Update `_has_dispatch_execution_meta` in
   `src/swe/app/crons/monitor_sync_client.py` to validate the complete dispatch
   identity.
4. Add focused predicate coverage for malformed and valid identities.
5. Run:
   `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_monitor_sync_client.py -q`
6. Run the related callback/B3 regression tests:
   `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_tenant_cron_api.py tests/unit/app/test_tenant_cron_execution.py tests/unit/app/test_runner_query_retry.py -q`
7. Review the final diff and run GitNexus `detect_changes`.

## Expected Files

- `src/swe/app/crons/monitor_sync_client.py`
- `tests/unit/app/test_monitor_sync_client.py`
- `docs/superpowers/plans/2026-07-15-cron-execution-feedback-routing-fix.md`
