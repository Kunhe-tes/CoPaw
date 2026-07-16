# Latest Cron Execution Subtask Count API

## Scope

- Add a gateway-facing Monitor read endpoint for the latest execution of a cron
  job.
- Scope the lookup with the gateway-provided `X-Source-Id` and the job's stored
  tenant identity.
- Return the selected execution identity and the number of rows in
  `swe_cron_subtasks` for its `trace_id`.
- Preserve the existing jobs and executions API contracts.

## Contract

`GET /api/monitor/external/cron/jobs/{job_id}/latest-execution/subtask-count`

Response when the job has an execution:

```json
{
  "job_id": "job-1",
  "execution_id": 42,
  "trace_id": "trace-1",
  "subtask_count": 7
}
```

Response when the job exists but has never executed:

```json
{
  "job_id": "job-1",
  "execution_id": null,
  "trace_id": null,
  "subtask_count": 0
}
```

- Return `404` when the job does not exist in the caller's `X-Source-Id`
  scope.
- Return `400` when the Gateway does not provide a non-empty `X-Source-Id`.
- Select the latest execution with `ORDER BY actual_time DESC, id DESC`.
- If that execution has no usable `trace_id`, return `subtask_count = 0`; do
  not fall back to an older execution.
- Authentication and source ownership validation remain the API Gateway's
  responsibility.

## External Router Organization

- All Gateway-facing Monitor APIs live in
  `monitor/src/monitor/app/routers/external.py`.
- The router owns the `/monitor/external` prefix and the reusable requirement
  for a non-empty Gateway-provided `X-Source-Id`.
- Domain query logic remains in its domain service; moving an endpoint into
  the external router does not move cron SQL into the router layer.
- The previous `/api/monitor/cron/jobs/{job_id}/latest-execution/subtask-count`
  path is removed because this endpoint has not been committed or published.

## TDD Tasks

1. Add focused service tests in
   `tests/unit/monitor/test_cron_latest_subtask_count.py`.
   - Job exists and latest execution has subtasks.
   - Job exists but has no execution.
   - Job is absent from the caller's source scope.
   - Latest execution has an empty trace ID.
   - Assert the execution query uses both `job_id` and stored `tenant_id`, and
     orders by `actual_time DESC, id DESC`.
2. Run the new tests and confirm they fail because the response model, service
   method, and route do not exist.
3. Add `LatestExecutionSubtaskCountResponse` to
   `monitor/src/monitor/app/models/cron.py`.
4. Add `QueryService.get_latest_execution_subtask_count()` to
   `monitor/src/monitor/app/services/cron/query_service.py`.
5. Add the GET route and reusable Gateway source requirement to
   `monitor/src/monitor/app/routers/external.py`.
6. Register the external router in
   `monitor/src/monitor/app/routers/__init__.py` and keep the endpoint out of
   `monitor/src/monitor/app/routers/cron.py`.
7. Re-run the focused tests, then related Monitor cron tests.

## Verification

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/monitor/test_cron_latest_subtask_count.py -q
& .\.venv\Scripts\python.exe -m pytest monitor/tests/test_query_api.py tests/unit/monitor/test_cron_overview_stats.py -q
```

- Run four review passes covering contract correctness, tenant/source
  isolation, SQL/cardinality behavior, and regression/test quality.
- Run GitNexus `detect_changes(scope="all")` before completion.
- Run `git diff --check` and inspect the final working-tree diff without
  touching the pre-existing execution-feedback changes.
