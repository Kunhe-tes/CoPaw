## MODIFIED Requirements

### Requirement: History section in sidebar
The sidebar SHALL display a "历史记录" section with a collapsible list below the task section. Each history item SHALL display a title (color #4F5060) and a timestamp (color #808191) in "YYYY-MM-DD HH:mm" format. Selecting a history item SHALL load that chat into the standard chat surface and preserve the same composer controls and Plan Mode active-state affordance used by new chats.

#### Scenario: History section display
- **WHEN** the sidebar is visible and history items exist
- **THEN** the "历史记录(N)" section shows history items with title and formatted timestamp

#### Scenario: History item click
- **WHEN** the user clicks a history item
- **THEN** the corresponding chat session is loaded (existing session navigation behavior)

#### Scenario: History chat composer shows active Plan Mode
- **WHEN** the user opens a historical chat whose metadata has `plan_mode_enabled` set to `true`
- **THEN** the loaded chat composer shows the same visible `计划模式` active button as the new-chat composer

#### Scenario: History chat composer hides inactive Plan Mode
- **WHEN** the user opens a historical chat whose metadata does not have `plan_mode_enabled` set to `true`
- **THEN** the loaded chat composer does not show the active `计划模式` button
