## MODIFIED Requirements

### Requirement: Cases management page
The system SHALL provide a featured-case management page at `/featured-cases-management` for exact-scope case CRUD and ordering operations.

#### Scenario: Operator opens management in a branch context
- **WHEN** an operator opens the page with a non-head-office BBK context
- **THEN** the page SHALL provide separate "本机构案例" and "总行案例" views
- **AND** each view SHALL use its own exact-scope total and pagination state

#### Scenario: Operator opens management in a head-office context
- **WHEN** an operator opens the page with a missing, blank, or `100` BBK context
- **THEN** the page SHALL display the head-office case scope without a redundant branch view

#### Scenario: Case table shows case information
- **WHEN** a management scope loads
- **THEN** the table SHALL display organization, title, ordering position, active status, and permitted operations

#### Scenario: Branch operator views head-office cases
- **WHEN** a non-head-office operator selects the "总行案例" view
- **THEN** the system SHALL display head-office cases as read-only
- **AND** the page SHALL explain that shared cases can only be managed from the head-office context

#### Scenario: Operator changes pages
- **WHEN** the operator changes the current page or page size
- **THEN** the system SHALL query only the selected logical scope using the selected pagination values

### Requirement: Case creation form
The system SHALL provide a drawer form for creating a case in the caller's writable featured-case scope.

#### Scenario: Operator opens the create form
- **WHEN** the operator activates "+ 新建案例" in a writable scope
- **THEN** the drawer SHALL open with fields for organization, title, prompt content, image URL, active status, iframe URL, iframe title, and steps
- **AND** the organization SHALL be derived from the current writable scope

#### Scenario: Operator saves a new case
- **WHEN** the operator submits valid case content
- **THEN** the system SHALL create the case at the end of the selected queue
- **AND** the page SHALL refresh the exact-scope case list

#### Scenario: Operator views a read-only scope
- **WHEN** a branch operator views the head-office scope
- **THEN** the page SHALL NOT expose a create action for that scope

### Requirement: Case editing form
The system SHALL provide a drawer form for editing case content in the caller's writable scope and a separate inline control for editing ordering position.

#### Scenario: Operator opens content editing
- **WHEN** the operator activates "编辑" on a writable case
- **THEN** the drawer SHALL open with the existing case content prefilled

#### Scenario: Operator saves edited content
- **WHEN** the operator submits valid content changes
- **THEN** the system SHALL update that case without changing its ordering position unless a dedicated reorder operation is submitted
- **AND** the page SHALL refresh the exact-scope case list

#### Scenario: Operator opens ordering editing
- **WHEN** the operator activates the visible edit icon beside a writable case's ordering number
- **THEN** only that cell SHALL enter the inline ordering interaction defined by `featured-case-ordering`

#### Scenario: Operator views a non-writable case
- **WHEN** a branch operator views a head-office case
- **THEN** the page SHALL NOT expose content-editing or ordering-editing controls

### Requirement: Case deletion with confirmation
The system SHALL require confirmation before deleting a writable case and SHALL compact the affected logical queue after deletion.

#### Scenario: Operator requests deletion
- **WHEN** the operator activates "删除" on a writable case
- **THEN** the system SHALL show a confirmation dialog identifying the target case

#### Scenario: Operator confirms deletion
- **WHEN** the operator confirms the destructive action
- **THEN** the system SHALL delete the case, renumber the affected exact-scope queue to contiguous positions, and refresh a valid page of that scope

#### Scenario: Operator views a read-only scope
- **WHEN** a branch operator views head-office cases
- **THEN** the page SHALL NOT expose deletion controls
