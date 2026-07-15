# Cron Batch Dispatch Fixes

## Scope
- Keep batch dispatch disabled on normal job creation unless the explicit enable endpoint is used.
- When an enabled batch parent is saved or refreshed, update the scheduler platform's batch callback job with the current cron and offset.
- Make scheduler-dispatched SWE callbacks carry `scopeId` and `fromId`, matching the external scheduler payload.
- Preserve real provider/model identity through batch intent creation and callback dispatch.
- Resolve the batch parent execution model in SWE before registering the batch scheduler job, then pass `provider_id` and `model_id` through scheduler `jobParam`.

## Implementation Steps
1. Add focused failing tests in scheduler service, internal callback router, and external cron refresh tests.
2. Update scheduler callback payload construction and dispatch metadata propagation.
3. Update batch parent save/refresh behavior so the normal scheduler job stays paused and the batch scheduler job is refreshed.
4. Make scheduler parent callbacks consume provider/model from `jobParam` instead of calling back into SWE.
5. Run targeted unit tests and GitNexus change detection.

## Verification
- `& .\.venv\Scripts\python.exe -m pytest tests/unit/scheduler/test_cron_scheduling_service.py tests/unit/routers/test_internal_tenant_scope.py tests/unit/app/test_external_cron_scope_refresh.py`
- `node .gitnexus/run.cjs detect_changes`
