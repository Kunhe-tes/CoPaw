## ADDED Requirements

### Requirement: Job-level notification delay metadata
Scheduled jobs SHALL accept an optional `meta.notification_delay_minutes` value representing the automatic success-notification delay in minutes.

#### Scenario: Missing metadata defaults to zero
- **WHEN** a scheduled job has no `meta.notification_delay_minutes`
- **THEN** the system treats its notification delay as `0` minutes

#### Scenario: Invalid metadata defaults to zero
- **WHEN** a scheduled job has a non-numeric, empty, or negative `meta.notification_delay_minutes`
- **THEN** the system treats its notification delay as `0` minutes

#### Scenario: Excessive metadata is capped
- **WHEN** a scheduled job has `meta.notification_delay_minutes` above seven days
- **THEN** the system caps the applied notification delay to seven days

### Requirement: Automatic run notification timing
For successful automatic agent scheduled runs, the system SHALL apply the job notification delay when calculating `notification_due_at`.

#### Scenario: Normal automatic run applies delay
- **WHEN** an automatic successful agent scheduled run completes at time `T` and the job has `notification_delay_minutes = 120`
- **THEN** the recorded execution notification due time is `T + 120 minutes`

#### Scenario: Manual run bypasses delay
- **WHEN** a manual successful agent scheduled run completes at time `T` and the job has `notification_delay_minutes = 120`
- **THEN** the recorded execution does not set a custom delayed due time and remains immediately claimable by the existing completion-notification default

### Requirement: Broadcast notification timing
Broadcast child jobs SHALL inherit the source job notification delay and automatic broadcast child executions SHALL add that delay on top of the existing broadcast offset.

#### Scenario: Broadcast child inherits delay
- **WHEN** a source scheduled job with `notification_delay_minutes = 120` is broadcast to target tenants
- **THEN** each child scheduled job stores `meta.notification_delay_minutes = 120`

#### Scenario: Automatic broadcast run stacks delay
- **WHEN** an automatic successful broadcast child run completes at time `T`, has `broadcast_offset_minutes = 20`, and has `notification_delay_minutes = 120`
- **THEN** the recorded execution notification due time is `T + 140 minutes`

#### Scenario: Manual broadcast run bypasses delays
- **WHEN** a manual successful broadcast child run completes at time `T`, has `broadcast_offset_minutes = 20`, and has `notification_delay_minutes = 120`
- **THEN** the recorded execution does not set a custom delayed due time and remains immediately claimable by the existing completion-notification default

### Requirement: CLI creation support
The `swe cron create` command SHALL support setting job notification delay metadata through an optional `--notification-delay-minutes` argument.

#### Scenario: CLI create omits delay
- **WHEN** `swe cron create` is run without `--notification-delay-minutes`
- **THEN** the generated job payload includes `meta.notification_delay_minutes = 0`

#### Scenario: CLI create sets delay
- **WHEN** `swe cron create` is run with `--notification-delay-minutes 120`
- **THEN** the generated job payload includes `meta.notification_delay_minutes = 120`

### Requirement: Console configuration and display
The Console SHALL allow users to configure notification delay with a numeric value and a unit of minutes or hours, and SHALL display the saved delay on the Cron Jobs list.

#### Scenario: Quick scheduled task popup saves hours as minutes
- **WHEN** a user creates a scheduled task with delay value `2` and unit `hours`
- **THEN** the created job payload stores `meta.notification_delay_minutes = 120`

#### Scenario: Cron Jobs drawer edits delay
- **WHEN** a user edits an existing job with `meta.notification_delay_minutes = 120`
- **THEN** the edit form shows value `2` and unit `hours`

#### Scenario: Cron Jobs list displays delay
- **WHEN** a job has `meta.notification_delay_minutes = 120`
- **THEN** the Cron Jobs list displays the notification delay as `2 hours`
