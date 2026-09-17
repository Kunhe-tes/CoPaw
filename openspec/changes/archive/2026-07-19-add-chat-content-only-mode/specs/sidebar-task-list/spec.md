## ADDED Requirements

### Requirement: Content-only presentation suppresses the chat sidebar

The Console SHALL treat content-only presentation as a visual exception to normal `ChatSidebar` rendering. When active, it SHALL omit the task section, history section, collapsed toolbar, and expandable task/history panels without changing their state, data, or normal-mode behavior.

#### Scenario: Expanded sidebar is suppressed

- **WHEN** a content-only chat opens while the persisted chat sidebar state is expanded
- **THEN** neither the task section nor the history section is rendered

#### Scenario: Collapsed sidebar is suppressed

- **WHEN** a content-only chat opens while the persisted chat sidebar state is collapsed
- **THEN** the collapsed toolbar and its expandable task/history panels are not rendered
- **AND** no suppressed sidebar control remains keyboard-focusable or present in the accessibility tree

#### Scenario: Normal chat restores sidebar presentation

- **WHEN** the user opens a chat without active content-only presentation
- **THEN** the existing task/history sections, pagination, collapsed toolbar, panels, and interactions remain available according to their current state
