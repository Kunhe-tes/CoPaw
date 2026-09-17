## Purpose

Define deterministic, isolated, and recoverable ordering behavior for featured-case queues across head-office and branch scopes.

## Requirements

### Requirement: Featured-case ordering SHALL be contiguous within one logical scope
The system SHALL maintain one ordering queue for each canonical `source_id + bbk_id` scope, SHALL assign every case in that queue exactly one integer position from `1` through the queue size, and SHALL include both active and inactive cases in the queue.

#### Scenario: Branch queues remain independent
- **WHEN** an administrator reorders a case belonging to branch `A`
- **THEN** the system SHALL renumber only the queue for the same `source_id` and branch `A`
- **AND** cases belonging to head office or any other branch SHALL retain their stored order

#### Scenario: Active and inactive cases share one queue
- **WHEN** a queue contains both active and inactive cases
- **THEN** the management order SHALL remain contiguous across all cases
- **AND** filtering inactive cases from runtime display SHALL preserve the relative order of the active cases

#### Scenario: Head-office identifiers form one logical scope
- **WHEN** existing head-office rows use `NULL`, an empty BBK value, or `100`
- **THEN** the ordering operation SHALL treat those rows as one head-office queue
- **AND** the mutation SHALL persist affected head-office rows with canonical BBK value `100`

### Requirement: Administrators SHALL move a case to an absolute position
The system SHALL accept a requested positive integer position, move the target case to that absolute position in its logical queue, preserve the relative order of all other cases, and normalize the resulting queue to `1..N`.

#### Scenario: Move a case toward the start
- **WHEN** the queue is `[A=1, B=2, C=3, D=4]` and the administrator moves `D` to position `2`
- **THEN** the resulting queue SHALL be `[A=1, D=2, B=3, C=4]`

#### Scenario: Move a case toward the end
- **WHEN** the queue is `[A=1, B=2, C=3, D=4]` and the administrator moves `B` to position `4`
- **THEN** the resulting queue SHALL be `[A=1, C=2, D=3, B=4]`

#### Scenario: Requested position exceeds queue size
- **WHEN** a queue contains 20 cases and the administrator requests position `30`
- **THEN** the system SHALL place the target case at position `20`

#### Scenario: Requested position is invalid
- **WHEN** the requested position is empty, non-numeric, fractional, zero, or negative
- **THEN** the system SHALL reject the request without changing any queue position

#### Scenario: Requested position is unchanged
- **WHEN** the requested position equals the target case's current position and the queue is already contiguous
- **THEN** the client SHALL exit edit mode without sending a reorder request

### Requirement: Queue-changing operations SHALL preserve continuity
The system SHALL preserve or restore contiguous queue positions whenever a case is created, reordered, or deleted.

#### Scenario: Create appends a case
- **WHEN** a case is created in a queue containing `N` cases
- **THEN** the new case SHALL receive position `N + 1`

#### Scenario: Delete closes the gap
- **WHEN** the case at position `K` is deleted from a queue containing `N` cases
- **THEN** surviving cases after position `K` SHALL move forward by one
- **AND** the resulting queue SHALL contain positions `1..N-1`

#### Scenario: Mutation repairs historical ordering defects
- **WHEN** an affected queue contains duplicate or discontinuous positions before a create, reorder, or delete
- **THEN** the system SHALL derive the stable existing order by `sort_order ASC, id ASC`
- **AND** the committed queue SHALL contain exactly the positions `1..N`

### Requirement: Queue mutations SHALL be atomic and serialized
The system SHALL apply every create, reorder, and delete as one transaction over the affected logical queue and SHALL roll back the entire mutation if any read or write fails.

#### Scenario: Reorder write fails
- **WHEN** any position update fails during a reorder
- **THEN** no case in the queue SHALL retain a partially updated position

#### Scenario: Concurrent reorders target the same queue
- **WHEN** two reorder requests for the same logical queue overlap
- **THEN** the system SHALL serialize them and apply each request to the latest committed queue
- **AND** the later committed request SHALL determine its target case's final requested position

#### Scenario: Concurrent reorders target different branches
- **WHEN** reorder requests affect different BBK queues under the same source
- **THEN** each request SHALL modify only its own queue

### Requirement: Inline ordering SHALL provide recoverable interaction states
The management table SHALL provide a discoverable inline ordering control for writable cases and SHALL keep the server as the authoritative source after each successful mutation.

#### Scenario: Administrator enters edit mode
- **WHEN** the administrator activates the sort edit control
- **THEN** the cell SHALL display a focused integer input prefilled with and selecting the current position
- **AND** the cell SHALL expose confirm and cancel actions without changing table row height

#### Scenario: Administrator commits a valid position
- **WHEN** the administrator presses Enter, activates confirm, or blurs a changed valid input
- **THEN** the client SHALL submit exactly one reorder request and disable competing sort actions until it completes

#### Scenario: Administrator cancels editing
- **WHEN** the administrator presses Escape or activates cancel
- **THEN** the cell SHALL restore the last server-confirmed position without a request

#### Scenario: Saving fails
- **WHEN** the reorder request fails
- **THEN** the input SHALL retain the attempted value and remain in edit mode
- **AND** the client SHALL show an actionable error and allow retry or cancellation

#### Scenario: Reorder crosses a page boundary
- **WHEN** the server confirms a final position that belongs to another management page
- **THEN** the client SHALL navigate to that exact-scope page, reload it from the server, and identify the moved row with success feedback
