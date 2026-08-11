## ADDED Requirements

### Requirement: Active Plan Mode composer button
The Console SHALL display an active `计划模式` composer button whenever the currently selected chat has `meta.plan_mode_enabled === true`.

#### Scenario: Plan Mode enabled on current chat
- **WHEN** the current chat metadata has `plan_mode_enabled` set to `true`
- **THEN** the composer action area shows a visible `计划模式` button

#### Scenario: Plan Mode disabled on current chat
- **WHEN** the current chat metadata does not have `plan_mode_enabled` set to `true`
- **THEN** the composer action area does not show the active `计划模式` button

### Requirement: Active Plan Mode button disables Plan Mode
The active `计划模式` composer button SHALL disable Plan Mode for the current chat when clicked.

#### Scenario: Disable from active button
- **WHEN** the active `计划模式` button is clicked
- **THEN** the frontend persists `plan_mode_enabled` as `false` for the current chat
- **AND** the active `计划模式` button is removed from the composer after persistence succeeds

#### Scenario: Disable persistence failure
- **WHEN** disabling Plan Mode from the active button fails
- **THEN** the frontend restores the visible Plan Mode state from the current chat metadata
- **AND** the user receives the existing Plan Mode persistence error message

### Requirement: Plan Mode visible labels are localized
The Console SHALL use `计划模式` for visible Plan Mode labels in composer controls and quick-menu entries.

#### Scenario: Quick menu label
- **WHEN** the quick menu contains the Plan Mode toggle entry
- **THEN** the entry label is `计划模式`

#### Scenario: Active button label
- **WHEN** Plan Mode is enabled and the active composer button is shown
- **THEN** the button text is `计划模式`

### Requirement: Internal Plan Mode protocol remains unchanged
The Console SHALL keep existing internal Plan Mode protocol values unchanged while localizing visible labels.

#### Scenario: Submit in Plan Mode
- **WHEN** a user submits a message while Plan Mode is enabled
- **THEN** the request metadata still uses `mode: "plan"`

#### Scenario: Submit outside Plan Mode
- **WHEN** a user submits a message while Plan Mode is disabled
- **THEN** the request metadata still uses `mode: "normal"`

### Requirement: Plan Mode state follows the selected chat
The active Plan Mode composer control SHALL follow the currently selected chat session and SHALL NOT leak from a previous chat.

#### Scenario: Switch from enabled chat to disabled chat
- **WHEN** the user switches from a chat with `plan_mode_enabled === true` to a chat without Plan Mode enabled
- **THEN** the active `计划模式` button is no longer shown after the target chat metadata is applied

#### Scenario: Switch from disabled chat to enabled chat
- **WHEN** the user switches from a chat without Plan Mode enabled to a chat with `plan_mode_enabled === true`
- **THEN** the active `计划模式` button is shown after the target chat metadata is applied
