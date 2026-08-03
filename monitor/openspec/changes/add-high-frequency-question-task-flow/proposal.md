# High Frequency Question Task Flow - Proposal

## Summary

Extend the existing high-frequency question monitor APIs with task submission,
24-hour result reuse, workflow dispatch, and result lookup.

## Motivation

The AI workflow is synchronous and writes final rows to
`swe_high_frequency_question_result`, but frontend requests must not wait for
the full workflow run. Monitor needs a lightweight task layer that records
submitted work in `swe_async_tasks`, reuses recent successful results for the
same source/date/scope, and exposes the latest result state to the frontend.

## Scope

- Add a task submission endpoint under the existing high-frequency question
  router.
- Add a scheduler-friendly prewarm endpoint that reuses the same submission
  logic.
- Add a result query endpoint that returns recent or stale successful results,
  or an empty state.
- Store task request criteria in `swe_async_tasks.result_json`.
- Dispatch the external workflow in an `asyncio` background task.
- Configure workflow URL, API key, open id, and response mode through
  environment-backed monitor configuration.

## API Impact

- `POST /api/monitor/high-frequency-question/tasks`
- `POST /api/monitor/high-frequency-question/prewarm`
- `GET /api/monitor/high-frequency-question/results`

Existing endpoints remain:

- `POST /api/monitor/high-frequency-question/messages`
- `POST /api/monitor/high-frequency-question/results`

## Decisions

- `source_id` is always preserved as the raw caller-provided source id.
- `swe_async_tasks.status` uses the existing lowercase status style:
  `running`, `succeeded`, `failed`.
- Submission does not deduplicate or reuse currently running tasks.
- Result lookup does not return running tasks.
- 24-hour reuse only applies to successful result rows in
  `swe_high_frequency_question_result`.
- The workflow call is considered successful only when the HTTP call succeeds
  and the JSON response contains `message = "success"`.
- If workflow completion is ambiguous or raises, Monitor checks whether rows
  already exist for `batch_id = task_id`; existing rows mark the task
  `succeeded`, otherwise the task is marked `failed`.

## Out of Scope

- Frontend implementation.
- Scheduler implementation.
- Database schema migrations.
- Workflow prompt or model logic.
- Running-task duplicate prevention.
