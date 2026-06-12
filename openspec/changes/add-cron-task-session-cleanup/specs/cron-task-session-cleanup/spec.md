## ADDED Requirements

### Requirement: Source config defines task session cleanup policy
The system SHALL define source-scoped `cron_task_session_cleanup` configuration with built-in defaults `enabled=false`, `retention_days=30`, and `cron="0 1 * * *"`. The system MUST treat `retention_days` as a positive integer and MUST accept only daily five-field cron values in the form `<minute> <hour> * * *`.

#### Scenario: Source inherits cleanup defaults
- **WHEN** a source has no explicit `cron_task_session_cleanup` config
- **THEN** the effective source system config SHALL disable scheduled task session cleanup
- **AND** it SHALL retain 30 days of history
- **AND** it SHALL schedule cleanup at `0 1 * * *`

#### Scenario: Invalid cleanup config is rejected
- **WHEN** a manager saves `cron_task_session_cleanup.retention_days=0`
- **THEN** the system SHALL reject the source system config update
- **WHEN** a manager saves `cron_task_session_cleanup.cron="*/5 * * * *"`
- **THEN** the system SHALL reject the source system config update

### Requirement: Cleanup runs as an external scheduler system job
The system SHALL register scheduled task session cleanup with the external scheduler platform as a system job for the current source. The cleanup system job MUST NOT be persisted as a business cron job, MUST NOT appear in user task lists, MUST NOT create its own task session, and MUST NOT participate in unread result, notification, or task result semantics.

#### Scenario: Cleanup config is enabled
- **WHEN** CronManager initializes for a source whose effective cleanup config is enabled
- **THEN** the system SHALL register or update an external scheduler system job with the configured daily cron
- **AND** the callback SHALL use a cleanup-specific `task_type`
- **AND** the external system job id SHALL be stored in the system jobs id store

#### Scenario: Cleanup config is enabled from the current source config page
- **WHEN** a manager saves the current source config with `cron_task_session_cleanup.enabled=true`
- **THEN** the system SHALL refresh the current Agent cleanup system job registration
- **AND** the external scheduler platform SHALL receive the configured daily cleanup job registration when a scheduler adapter is available

#### Scenario: Cleanup config is disabled
- **WHEN** CronManager initializes for a source whose effective cleanup config is disabled
- **THEN** the system SHALL pause the existing external scheduler cleanup job when one is known
- **AND** it SHALL NOT create or update a business cron job in `jobs.json`

#### Scenario: Cleanup callback dispatches
- **WHEN** the internal scheduler callback receives the cleanup `task_type`
- **THEN** it SHALL dispatch to the CronManager cleanup runner for the resolved runtime tenant and agent
- **AND** it SHALL NOT require a business `job_id`

### Requirement: Cleanup prunes only filesystem task session history
The cleanup runner SHALL prune filesystem task session history older than the configured retention window. It MUST NOT delete business cron jobs, task chats, chat/session bindings, cron execution records, monitor data, tracing data, token usage data, or other audit records.

#### Scenario: Expired task run history is pruned
- **WHEN** a task session contains `task_runs` whose `ended_at` values are older than the retention cutoff
- **THEN** cleanup SHALL remove those run records
- **AND** it SHALL remove the corresponding `agent.memory.content` slices for those runs
- **AND** it SHALL preserve non-expired run records and their memory content

#### Scenario: All task history is expired
- **WHEN** every reliable task run and task message in a task session is older than the retention cutoff
- **THEN** cleanup SHALL reduce the session JSON to a minimal state without old task history
- **AND** it SHALL keep the business task, task chat id, task session id, and creator user id bindings intact outside the session file

#### Scenario: Audit stores are not touched
- **WHEN** cleanup removes old filesystem task session history
- **THEN** rows in cron execution stores, monitor records, and tracing stores SHALL remain unchanged

### Requirement: Cleanup preserves ambiguous or malformed history
The cleanup runner SHALL preserve records whose retention eligibility cannot be determined reliably.

#### Scenario: Task run has no reliable timestamp
- **WHEN** a task run is missing `ended_at` or has an unparsable `ended_at`
- **THEN** cleanup SHALL keep that task run
- **AND** it SHALL log that the record was skipped for ambiguous time data

#### Scenario: Task run memory range is invalid
- **WHEN** a task run has `memory_start` or `memory_end` values that do not map safely to `agent.memory.content`
- **THEN** cleanup SHALL keep that task run and its session state
- **AND** it SHALL log that the record was skipped for invalid memory range data

### Requirement: Cleanup recomputes only derived task display metadata
After pruning a task session, the system SHALL update only derived scheduled-task display metadata in the business job record. It MUST preserve task identity, task/chat/session bindings, origin metadata, subscription metadata, schedule settings, notification settings, model/source settings, enabled state, pause reason, and auto-pause metadata.

#### Scenario: Remaining history exists after cleanup
- **WHEN** cleanup leaves at least one reliable non-expired scheduled task result
- **THEN** `task_has_scheduled_result` SHALL be `true`
- **AND** `task_last_scheduled_preview` SHALL reflect the latest remaining result preview
- **AND** `task_last_scheduled_run_at` SHALL reflect the latest remaining result time
- **AND** `task_unread_execution_count` SHALL be reset to `0`

#### Scenario: No history remains after cleanup
- **WHEN** cleanup leaves no reliable scheduled task result history
- **THEN** `task_has_scheduled_result` SHALL be `false`
- **AND** `task_last_scheduled_preview` SHALL be empty
- **AND** `task_last_scheduled_run_at` SHALL be `null`
- **AND** `task_unread_execution_count` SHALL be `0`

#### Scenario: Auto-paused task remains paused
- **WHEN** a task was paused before cleanup because of unread auto-pause
- **THEN** cleanup SHALL NOT re-enable the task
- **AND** the task MAY show zero unread executions while remaining paused

### Requirement: Cleanup coordinates with task session writes
The cleanup runner and cron task session save path SHALL coordinate writes by task session id. Cleanup MUST NOT skip all history for a task solely because a run is currently active; it MAY skip a specific session when it cannot obtain the session write lock within the configured short timeout.

#### Scenario: Active task does not block old-history cleanup forever
- **WHEN** a business task runs at the same daily time as the cleanup system job
- **THEN** cleanup SHALL attempt to acquire the task session write lock
- **AND** if it obtains the lock, it SHALL prune expired historical runs without affecting the active run that has not yet been written

#### Scenario: Session write lock is unavailable
- **WHEN** cleanup cannot obtain the task session write lock before timeout
- **THEN** cleanup SHALL skip that session for the current run
- **AND** it SHALL log the skipped session
- **AND** a later cleanup run SHALL be able to retry the same session
