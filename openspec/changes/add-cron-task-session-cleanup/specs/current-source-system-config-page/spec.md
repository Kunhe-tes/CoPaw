## ADDED Requirements

### Requirement: Current source config page SHALL manage scheduled task session cleanup
The current source system config page SHALL expose controls for `cron_task_session_cleanup.enabled`, `cron_task_session_cleanup.retention_days`, and daily run time for the active request source. The page MUST preserve unknown raw config keys when saving this section.

#### Scenario: Page loads cleanup defaults
- **WHEN** a manager opens the current source system config page for a source with no explicit cleanup config
- **THEN** the page SHALL show scheduled task session cleanup disabled
- **AND** it SHALL show retention days as `30`
- **AND** it SHALL show daily run time as `01:00`

#### Scenario: Manager saves cleanup config
- **WHEN** a manager changes cleanup retention to `45` days and daily run time to `02:30`
- **THEN** the Console SHALL save `cron_task_session_cleanup.retention_days=45`
- **AND** it SHALL save `cron_task_session_cleanup.cron="30 2 * * *"`
- **AND** it SHALL preserve unrelated raw config keys from the fetched source config

#### Scenario: Manager disables cleanup
- **WHEN** a manager turns off scheduled task session cleanup and saves
- **THEN** the Console SHALL save `cron_task_session_cleanup.enabled=false`
- **AND** the effective config refresh after save SHALL expose the disabled value to later requests under the same active source

#### Scenario: Cleanup form validates daily settings
- **WHEN** a manager enters a retention value less than `1`
- **THEN** the page SHALL prevent saving and show validation feedback
- **WHEN** a manager enters an invalid daily run time
- **THEN** the page SHALL prevent saving and show validation feedback
