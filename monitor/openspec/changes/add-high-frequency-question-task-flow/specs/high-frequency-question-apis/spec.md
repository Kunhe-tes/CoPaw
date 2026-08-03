# high-frequency-question-apis Specification

## ADDED Requirements

### Requirement: High-Frequency Question Task Submission

The monitor service SHALL provide a high-frequency question task submission API
that reuses recent successful results or starts a background workflow task.

#### Scenario: Reuse recent successful result on submission

- **GIVEN** a request to `POST /api/monitor/high-frequency-question/tasks`
- **AND** the request contains `source_id`, `start_time`, and `end_time`
- **WHEN** a successful result batch exists for the same `source_id`, start
  date, end date, normalized `scope_type`, and normalized `bbk_id`
- **AND** that batch's latest `created_at` is within the last 24 hours
- **THEN** the service returns the existing `batch_id`, result state, update
  time, and topics
- **AND** does not create a new `swe_async_tasks` row.

#### Scenario: Create background task when no recent result exists

- **GIVEN** a valid task submission request
- **WHEN** no 24-hour successful result exists for the same normalized criteria
- **THEN** the service creates a `swe_async_tasks` row with `service = monitor`
- **AND** uses `task_type = monitor.high.freq.question`
- **AND** uses lowercase `status = running`
- **AND** stores the raw `source_id` in the `source_id` column
- **AND** stores the normalized criteria under `result_json.request`
- **AND** schedules the configured workflow outside the task creation write
- **AND** immediately returns the new `task_id` and `state = RUNNING`.

#### Scenario: Submission does not deduplicate running tasks

- **GIVEN** a valid task submission request
- **AND** a matching `swe_async_tasks` row already has `status = running`
- **WHEN** no 24-hour successful result exists
- **THEN** the service may create another task for the same criteria
- **AND** MUST NOT block submission because of the running task.

### Requirement: High-Frequency Question Workflow Completion

The monitor service SHALL update high-frequency question task records after the
external workflow finishes or fails.

#### Scenario: Mark task succeeded after workflow success

- **GIVEN** a high-frequency question task has been created
- **WHEN** the workflow HTTP call succeeds
- **AND** the response JSON contains `message = "success"`
- **AND** result rows exist for `source_id + batch_id`
- **THEN** the service updates the task status to `succeeded`
- **AND** sets `done_count = 1`, `failed_count = 0`, `finished_at`, and
  result metadata in `result_json.result`.

#### Scenario: Resolve ambiguous workflow failure through result rows

- **GIVEN** a high-frequency question task has been created
- **WHEN** the workflow call raises or returns an unexpected response
- **AND** result rows exist for `source_id + batch_id`
- **THEN** the service updates the task status to `succeeded`.

#### Scenario: Mark task failed when workflow does not write results

- **GIVEN** a high-frequency question task has been created
- **WHEN** the workflow call raises or returns an unexpected response
- **AND** no result rows exist for `source_id + batch_id`
- **THEN** the service updates the task status to `failed`
- **AND** stores only a truncated safe error summary.

### Requirement: High-Frequency Question Prewarm

The monitor service SHALL provide a scheduler-friendly prewarm API that reuses
the same submission logic.

#### Scenario: Submit default seven-day ALL-scope prewarm

- **GIVEN** a request to `POST /api/monitor/high-frequency-question/prewarm`
- **AND** the request contains `source_id`
- **WHEN** no explicit time range is provided
- **THEN** the service submits a task for the most recent seven-day range
- **AND** uses normalized `scope_type = ALL` and `bbk_id = ALL`
- **AND** records actor fields as system scheduler values.

### Requirement: High-Frequency Question Result Lookup

The monitor service SHALL provide a result lookup API that only returns
successful result rows for the caller's source.

#### Scenario: Return recent available results

- **GIVEN** a request to `GET /api/monitor/high-frequency-question/results`
- **AND** the query contains `source_id`, `start_time`, and `end_time`
- **WHEN** a successful result batch exists for the same normalized criteria
- **AND** the batch's latest `created_at` is within the last 24 hours
- **THEN** the service returns `state = AVAILABLE`
- **AND** returns `result_updated_at` from the batch's maximum `created_at`
- **AND** returns topic rows from that batch.

#### Scenario: Return stale successful results

- **GIVEN** a valid result lookup request
- **WHEN** no 24-hour successful result exists
- **AND** an older successful result exists for the same normalized criteria
- **THEN** the service returns `state = AVAILABLE_STALE`
- **AND** includes the stale message
- **AND** returns the older successful topic rows.

#### Scenario: Return empty state

- **GIVEN** a valid result lookup request
- **WHEN** no successful result exists for the same normalized criteria
- **THEN** the service returns `state = EMPTY`
- **AND** does not inspect running tasks.
