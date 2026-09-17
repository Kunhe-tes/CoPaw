## ADDED Requirements

### Requirement: Broadcast submission starts a background task
The system SHALL start scheduled-job broadcast work in the background and return a task summary without waiting for all target tenants to finish.

#### Scenario: Broadcast submission returns started task
- **WHEN** a manager submits a broadcast request for a source Scheduled Job with valid target tenants
- **THEN** the API response SHALL include a broadcast task id, status `running`, target tenant count, and zero completed targets
- **AND** the API request SHALL NOT wait for every target tenant to complete broadcast processing

#### Scenario: Duplicate running submission is reused
- **WHEN** a manager submits a broadcast for a source Scheduled Job while any broadcast task for that source Scheduled Job is still running
- **THEN** the API SHALL return the running task summary instead of creating a second concurrent task for the same source job

### Requirement: Broadcast task progress is queryable
The system SHALL expose the current progress and per-target results for a broadcast task by task id.

#### Scenario: Query running task
- **WHEN** a manager queries a running broadcast task
- **THEN** the response SHALL include status `running`, total target count, completed count, failed count, and any target results already recorded

#### Scenario: Query completed task
- **WHEN** all target tenants have finished broadcast processing
- **THEN** the task query response SHALL include status `completed` if every target succeeded
- **AND** the response SHALL include one per-target result for each selected tenant

#### Scenario: Query task with target failures
- **WHEN** one or more target tenants fail while at least one target tenant succeeds
- **THEN** the task query response SHALL include the successful target results and failed target error details
- **AND** the task status SHALL be `failed`

#### Scenario: Query current running task for a source job
- **WHEN** a manager opens the broadcast modal for a source Scheduled Job
- **THEN** the API SHALL return the currently running broadcast task for that source Scheduled Job if one exists
- **AND** the API SHALL return no task when there is no running broadcast for that source Scheduled Job

### Requirement: Broadcast progress is persisted when database storage is available
The system SHALL persist broadcast task and target progress when the application has a connected database, and SHALL fall back to process memory otherwise.

#### Scenario: Database-backed progress
- **WHEN** database storage is connected during app startup
- **THEN** broadcast task status and target result rows SHALL be written to database tables
- **AND** a later task status query in the same deployment SHALL return the persisted progress

#### Scenario: Memory fallback progress
- **WHEN** database storage is unavailable during app startup
- **THEN** broadcast task status and target result rows SHALL be kept in process memory
- **AND** the broadcast submission and task lookup APIs SHALL still function within that process

### Requirement: Broadcast target processing is idempotent per source job and target tenant
The system SHALL avoid duplicate child Scheduled Jobs when a broadcast is repeated for a target tenant that already has a child of the same source Scheduled Job.

#### Scenario: Existing child job is refreshed
- **WHEN** a target tenant already has a child Scheduled Job whose metadata references the source Scheduled Job
- **THEN** broadcast processing for that target tenant SHALL refresh the existing child job
- **AND** the system SHALL NOT create a second child Scheduled Job for that target tenant and source Scheduled Job

#### Scenario: New child job is created once
- **WHEN** a target tenant does not have a child Scheduled Job for the source Scheduled Job
- **THEN** broadcast processing SHALL create one child Scheduled Job for that target tenant
- **AND** the broadcast task result SHALL include the created child job id

### Requirement: Console shows current broadcast progress without continuous polling
The Console SHALL show broadcast submission as a running task and SHALL query the current running task when the broadcast modal opens.

#### Scenario: Console shows started task after submit
- **WHEN** a manager confirms scheduled-job broadcast in the Cron Jobs page
- **THEN** the modal SHALL show that broadcast has started
- **AND** the Console SHALL stop waiting for final per-target results in the submit request

#### Scenario: Console checks current running task on open
- **WHEN** a manager opens the broadcast modal for a Scheduled Job
- **THEN** the Console SHALL request the current running broadcast task once
- **AND** the Console SHALL show the running progress if a task is returned
- **AND** the Console SHALL disable starting another broadcast while that task is running
