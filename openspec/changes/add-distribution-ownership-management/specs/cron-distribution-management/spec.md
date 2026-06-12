## ADDED Requirements

### Requirement: Scheduled job child lookup
The system SHALL let managers query broadcast child scheduled jobs for any source scheduled job.

#### Scenario: Source job has no children
- **WHEN** a manager queries broadcast children for a scheduled job with no child jobs
- **THEN** the response contains an empty list and no error

#### Scenario: Source job has distributed children
- **WHEN** a target tenant has a scheduled job whose `meta.broadcast_source_job_id` equals the source job ID
- **THEN** the lookup response includes that child job with tenant identity, enabled state, cron schedule, and last runtime state when available

### Requirement: Batch delete broadcast children
The system SHALL allow managers to delete selected broadcast child scheduled jobs for a source scheduled job without deleting the source job.

#### Scenario: Selected child belongs to source
- **WHEN** a manager requests deletion of a child job whose `broadcast_source_job_id` equals the source job ID
- **THEN** the child job is deleted from its target tenant

#### Scenario: Selected child does not belong to source
- **WHEN** a manager requests deletion of a job that does not point to the source job ID
- **THEN** the system does not delete it and returns a failed result for that item

### Requirement: Batch rerun broadcast children
The system SHALL allow managers to rerun selected enabled broadcast child scheduled jobs for a source scheduled job.

#### Scenario: Enabled child reruns
- **WHEN** a selected child job belongs to the source job and is enabled
- **THEN** the system triggers the existing manual run path for that child job

#### Scenario: Disabled child is skipped
- **WHEN** a selected child job belongs to the source job but is disabled or paused
- **THEN** the system does not run it and returns a skipped result with the reason "paused, not executed"

### Requirement: Rebroadcast overwrites task definition only
When a source scheduled job is rebroadcast to a tenant that already has a child job, the system SHALL update only task-definition and execution-configuration fields on the child job.

#### Scenario: Existing child preserves target identity and enabled state
- **WHEN** rebroadcast finds an existing child job for a target tenant
- **THEN** the child keeps its job ID, tenant identity, dispatch target identity, task binding metadata, and current enabled state
- **AND** the child receives the source job's task content, task type, schedule, runtime, model slot, and source-derived broadcast metadata
