# High Frequency Question APIs - Implementation Proposal

## Timeline

- **Date**: 2026-07-30
- **Status**: In Progress

## Components

### 1. Source Message Query

Add a monitor endpoint that returns clean user messages from `swe_tracing_traces` for the AI workflow.

Filtering rules:
- `source_id` is required in the request body.
- `start_time <= swe_tracing_traces.start_time < end_time`.
- Only `status = 'completed'`.
- Exclude scheduled task traces where `session_id LIKE 'cron-task%'`.
- Use `user_message` as the user message content.
- Exclude NULL, blank, and fixed meaningless short text values.
- Optional exact `bbk_id` filter.
- Return in ascending `start_time` order.
- Query up to 10001 rows and fail when more than 10000 rows match.

### 2. Result Batch Save

Add a monitor endpoint that saves AI-generated topic ranking results into `swe_high_frequency_question_result`.

Persistence rules:
- Validate all rows before writing.
- Support `scope_type` values `ALL` and `ORG`.
- Enforce per-batch uniqueness for `batch_id + scope_type + bbk_id + rank_no`.
- Limit `rank_no` to 1 through 10.
- Limit `sample_questions` to at most 4 items, each at most 1000 characters.
- Store `sample_questions` as JSON text through the existing MySQL driver.
- In one transaction, delete existing rows for the same `batch_id`, then batch insert the full replacement set.

## API Impact

- `POST /api/monitor/high-frequency-question/messages`
- `POST /api/monitor/high-frequency-question/results`

## Out of Scope

- Frontend pages
- Scheduler jobs
- LLM calls
- Prompt or topic classification logic
- Top 10 computation
- Result display query APIs
- New database table creation
