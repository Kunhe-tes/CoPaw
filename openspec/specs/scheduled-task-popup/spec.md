# scheduled-task-popup Specification

## Purpose
Define the scheduled task popup behavior for creating cron jobs from case details, including execution schedule selection and optional execution model selection.

## Requirements

### Requirement: Popup modal display
When the user clicks "订阅为定时任务" in the CaseDetailDrawer, the system SHALL display a modal popup titled "定时设置" with frequency selection tabs (每天/每周/每月), time picker, and confirm/cancel buttons.

#### Scenario: Open popup from CaseDetailDrawer
- **WHEN** user clicks the "订阅为定时任务" button in CaseDetailDrawer
- **THEN** the ScheduledTaskPopup modal is displayed with default frequency "每天" and time "09:00"

#### Scenario: Close popup via cancel button
- **WHEN** user clicks the "取消" button in the popup
- **THEN** the popup closes without creating a scheduled task

#### Scenario: Close popup via close icon
- **WHEN** user clicks the "✕" close button in the popup header
- **THEN** the popup closes without creating a scheduled task

#### Scenario: Close popup via backdrop click
- **WHEN** user clicks outside the modal content area
- **THEN** the popup closes without creating a scheduled task

### Requirement: Frequency tab selection
The popup SHALL display three frequency tabs (每天/每周/每月). Switching tabs SHALL reset detailed settings to default values for that frequency type.

#### Scenario: Switch to weekly frequency
- **WHEN** user clicks the "每周" tab
- **THEN** the weekday selector is displayed with Monday selected by default, and the time picker shows default time

#### Scenario: Switch to monthly frequency
- **WHEN** user clicks the "每月" tab
- **THEN** the date selector grid is displayed with day 1 selected by default, and the time picker shows default time

#### Scenario: Switch back to daily frequency
- **WHEN** user switches from weekly/monthly to "每天" tab
- **THEN** only the time picker is displayed, no weekday/date selector

### Requirement: Time picker input
The popup SHALL display a time picker with hour and minute input fields. Input SHALL be validated and auto-formatted on blur.

#### Scenario: Valid time input
- **WHEN** user enters "09" in hour field and "30" in minute field
- **THEN** the time is stored as "09:30" and preview updates accordingly

#### Scenario: Invalid hour auto-correction
- **WHEN** user enters "25" in hour field and the field loses focus
- **THEN** the value is auto-corrected to "23" (maximum valid hour)

#### Scenario: Invalid minute auto-correction
- **WHEN** user enters "99" in minute field and the field loses focus
- **THEN** the value is auto-corrected to "59" (maximum valid minute)

#### Scenario: Auto-zero padding
- **WHEN** user enters "9" in hour field and the field loses focus
- **THEN** the value is formatted to "09" with zero padding

### Requirement: Weekday multi-select (weekly mode)
In weekly frequency mode, the popup SHALL display a weekday selector grid (一/二/三/四/五/六/日). Users SHALL be able to select multiple weekdays. At least one weekday MUST be selected.

#### Scenario: Select multiple weekdays
- **WHEN** user clicks on "一", "三", "五" in the weekday grid
- **THEN** those three days are visually highlighted as selected

#### Scenario: Toggle weekday selection
- **WHEN** user clicks on an already-selected weekday (e.g., "一")
- **THEN** that weekday is deselected and removed from the selection

#### Scenario: Prevent zero weekday selection
- **WHEN** user attempts to deselect the last remaining selected weekday
- **THEN** the deselection is prevented and at least one weekday remains selected

#### Scenario: Preview shows weekday pattern
- **WHEN** user selects weekdays 一/三/五 with time 10:00
- **THEN** the preview displays "每周一三五执行" and calculates the next execution day

### Requirement: Date multi-select (monthly mode)
In monthly frequency mode, the popup SHALL display a date selector grid (1-31). Users SHALL be able to select multiple dates. At least one date MUST be selected.

#### Scenario: Select multiple dates
- **WHEN** user clicks on dates 1, 15 in the date grid
- **THEN** those dates are visually highlighted as selected

#### Scenario: Toggle date selection
- **WHEN** user clicks on an already-selected date (e.g., 15)
- **THEN** that date is deselected and removed from the selection

#### Scenario: Prevent zero date selection
- **WHEN** user attempts to deselect the last remaining selected date
- **THEN** the deselection is prevented and at least one date remains selected

#### Scenario: Preview shows date pattern
- **WHEN** user selects dates 1, 15 with time 10:00
- **THEN** the preview displays "每月1日、15日执行" and calculates the next execution date

#### Scenario: Date 29/30/31 boundary warning
- **WHEN** user selects date 29, 30, or 31
- **THEN** a warning tooltip is displayed indicating "部分月份不存在该日期，将顺延至当月最后一天执行"

### Requirement: Execution preview
The popup SHALL display a preview section showing the next execution time and execution pattern summary. The preview SHALL update in real-time as user changes settings.

#### Scenario: Daily preview
- **WHEN** user selects daily frequency with time 09:00
- **THEN** the preview displays "明天 09:00 首次执行，每天自动执行"

#### Scenario: Weekly preview
- **WHEN** user selects weekly frequency with weekdays 一/三/五 and time 10:00
- **THEN** the preview displays "下周X 10:00 首次执行，每周一三五执行" where X is the next selected weekday

#### Scenario: Monthly preview
- **WHEN** user selects monthly frequency with dates 1, 15 and time 10:00
- **THEN** the preview displays "下月X日 10:00 首次执行，每月1日、15日执行" where X is the next selected date

### Requirement: Confirm button state
The confirm button SHALL be enabled only when all required fields have valid values (time is valid + at least one execution day selected for weekly/monthly modes).

#### Scenario: Confirm button disabled for invalid time
- **WHEN** the time input is empty or contains invalid values
- **THEN** the confirm button is disabled

#### Scenario: Confirm button disabled for no weekday selection
- **WHEN** in weekly mode and no weekdays are selected
- **THEN** the confirm button is disabled

#### Scenario: Confirm button enabled for valid daily config
- **WHEN** in daily mode with valid time (e.g., 09:00)
- **THEN** the confirm button is enabled

### Requirement: Cron expression generation
When the user confirms the popup, the system SHALL generate a valid cron expression from the user's selections.

#### Scenario: Generate daily cron expression
- **WHEN** user confirms daily frequency with time 09:00
- **THEN** cron expression `0 0 9 * * *` is generated (0 minute, 9 hour, every day)

#### Scenario: Generate weekly cron expression
- **WHEN** user confirms weekly frequency with weekdays 一/三/五 (1,3,5) and time 10:00
- **THEN** cron expression `0 0 10 * * 1,3,5` is generated

#### Scenario: Generate monthly cron expression
- **WHEN** user confirms monthly frequency with dates 1, 15 and time 10:00
- **THEN** cron expression `0 0 10 1,15 * *` is generated

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
