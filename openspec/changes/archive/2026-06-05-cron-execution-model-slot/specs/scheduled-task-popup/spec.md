## ADDED Requirements

### Requirement: Execution model selection
The scheduled task popup SHALL allow users to choose between the tenant default model and an explicit configured provider/model when creating an agent scheduled task from case details.

#### Scenario: Popup defaults to tenant default model
- **WHEN** the ScheduledTaskPopup opens
- **THEN** the execution model selector SHALL default to tenant default model
- **AND** confirming the popup in that state SHALL create a cron job without `model_slot`

#### Scenario: Popup submits explicit model slot
- **WHEN** the user selects a configured provider/model in the ScheduledTaskPopup and confirms
- **THEN** the created cron job payload SHALL include top-level `model_slot` with the selected `provider_id` and `model`

#### Scenario: Popup only lists configured tenant models
- **WHEN** the ScheduledTaskPopup loads execution model options
- **THEN** it SHALL list only provider/model choices from the current tenant's configured providers and their `models + extra_models`

## MODIFIED Requirements

### Requirement: Scheduled task creation
When the user confirms the popup with valid settings, the system SHALL create a scheduled task via the cronjob API using the case data from the parent component and the selected execution model behavior.

#### Scenario: Create scheduled task from case
- **WHEN** user confirms popup with caseData present and valid settings
- **THEN** a CronJobSpecInput is created with schedule.cron from generated expression, dispatch targeting the current user/session, and the case input data

#### Scenario: Create scheduled task with default model
- **WHEN** user confirms popup while the execution model selector is set to tenant default model
- **THEN** the CronJobSpecInput SHALL NOT include `model_slot`

#### Scenario: Create scheduled task with explicit model
- **WHEN** user confirms popup after selecting a configured provider/model
- **THEN** the CronJobSpecInput SHALL include top-level `model_slot` with the selected provider and model

#### Scenario: API success feedback
- **WHEN** the cronjob creation API call succeeds
- **THEN** the popup closes and a success message is displayed (e.g., toast notification "定时任务创建成功")

#### Scenario: API error feedback
- **WHEN** the cronjob creation API call fails
- **THEN** an error message is displayed in the popup and the popup remains open for user to retry
