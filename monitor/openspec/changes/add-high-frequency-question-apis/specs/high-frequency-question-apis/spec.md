# high-frequency-question-apis Specification

## ADDED Requirements

### Requirement: Source Message Query API

The monitor service SHALL provide a source message query API for high-frequency question analysis.

#### Scenario: Query clean user messages

- **GIVEN** a request to `POST /api/monitor/high-frequency-question/messages`
- **AND** the request body contains `source_id`, `start_time`, and `end_time`
- **WHEN** `start_time` is earlier than `end_time` and the time range is at most 31 days
- **THEN** the service queries `swe_tracing_traces` using parameter binding
- **AND** filters by `source_id = request.source_id`
- **AND** filters by `start_time >= request.start_time`
- **AND** filters by `start_time < request.end_time`
- **AND** filters by `status = 'completed'`
- **AND** excludes rows where `session_id` starts with `cron-task`
- **AND** excludes NULL, blank, and configured meaningless `user_message` values
- **AND** applies the optional exact `bbk_id` filter when provided
- **AND** returns rows ordered by `start_time ASC, trace_id ASC`.

#### Scenario: Reject oversized message result

- **GIVEN** a valid source message query request
- **WHEN** more than 10000 rows match the query
- **THEN** the service returns an explicit client error
- **AND** does not silently truncate the response.

### Requirement: Result Batch Save API

The monitor service SHALL provide an idempotent batch save API for AI-generated high-frequency question analysis results.

#### Scenario: Save a complete result batch

- **GIVEN** a request to `POST /api/monitor/high-frequency-question/results`
- **AND** the request body contains `batch_id`, `stat_start_time`, `stat_end_time`, and non-empty `results`
- **WHEN** all result rows pass validation
- **THEN** the service opens one database transaction
- **AND** deletes existing rows from `swe_high_frequency_question_result` for the same `batch_id`
- **AND** batch inserts the new rows
- **AND** commits the transaction.

#### Scenario: Roll back failed result save

- **GIVEN** a valid result save request
- **WHEN** the delete or batch insert fails
- **THEN** the service rolls back the transaction
- **AND** leaves previously committed rows for other `batch_id` values unaffected.

#### Scenario: Reject invalid result rows

- **GIVEN** a result save request
- **WHEN** `scope_type`, `bbk_id`, `rank_no`, topic text, counts, duplicate rank keys, or `sample_questions` violate validation rules
- **THEN** the service rejects the request before writing to the database.
