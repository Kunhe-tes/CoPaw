## ADDED Requirements

### Requirement: Session SHALL persist confirmed associated skill freshness baselines
The system SHALL persist a top-level session skill snapshot for each chat session. The snapshot SHALL only include skills that have reached confirmed association during a turn, and each snapshot entry SHALL store at least the skill name, the resolved skill directory, and the current freshness token for that directory.

#### Scenario: Confirmed skill association creates a snapshot entry immediately
- **WHEN** a skill becomes confirmed for the current session during a turn
- **THEN** the system SHALL persist a session snapshot entry for that skill in the same turn without waiting for turn completion
- **AND** the entry SHALL contain the skill name, resolved skill directory, and freshness token

#### Scenario: Low-confidence inference does not expand the snapshot
- **WHEN** the runtime only infers that a skill may be relevant but does not actually activate that skill
- **THEN** the system SHALL NOT add that skill to the session skill snapshot

#### Scenario: Snapshot state is stored outside agent state
- **WHEN** the session state is saved after a turn that has one or more confirmed associated skills
- **THEN** the session skill snapshot SHALL be stored as a top-level session state key
- **AND** the snapshot SHALL NOT be nested under the persisted `agent` state

### Requirement: Next-turn startup SHALL detect effective associated skill changes
At the start of each turn, after loading session state and before rebuilding the system prompt, the system SHALL compare the stored session skill snapshot against the current effective skill resolution for that turn and detect effective associated skill changes.

#### Scenario: Matching directory with unchanged freshness token does not refresh
- **WHEN** a stored associated skill resolves to the same skill directory for the current turn
- **AND** the current freshness token matches the stored freshness token
- **THEN** the system SHALL treat that skill as unchanged for the current turn

#### Scenario: Directory freshness token change triggers refresh
- **WHEN** a stored associated skill resolves to the same skill directory for the current turn
- **AND** the current freshness token differs from the stored freshness token
- **THEN** the system SHALL treat that skill as changed for the current turn
- **AND** the system SHALL trigger a skill freshness refresh before the turn executes

#### Scenario: Directory switch triggers refresh
- **WHEN** a stored associated skill name resolves to a different skill directory than the one stored in the session snapshot
- **THEN** the system SHALL treat that directory switch as a real associated skill change
- **AND** the system SHALL trigger a skill freshness refresh before the turn executes

#### Scenario: Effective skill withdrawal triggers refresh
- **WHEN** a stored associated skill is still present on disk
- **AND** that skill is no longer part of the current turn's effective skill set
- **THEN** the system SHALL treat that skill as withdrawn for the current turn
- **AND** the system SHALL trigger a skill freshness refresh before the turn executes

#### Scenario: Missing associated skill is ignored and removed
- **WHEN** a stored associated skill directory no longer exists at next-turn freshness-check time
- **THEN** the system SHALL continue the turn without treating that skill as a change
- **AND** the system SHALL silently remove that stale snapshot entry

### Requirement: Skill freshness refresh SHALL rebuild prompt state and emit one model-only aggregated notice
When the system detects one or more effective associated skill changes for a turn, it SHALL rebuild prompt state for that turn and emit exactly one model-only aggregated skill freshness notice for the affected turn.

#### Scenario: Multiple changed skills produce one aggregated notice
- **WHEN** the current turn detects effective associated skill changes for multiple skills
- **THEN** the system SHALL emit exactly one aggregated skill freshness notice for that turn
- **AND** the notice SHALL list each affected skill and its change type item-by-item

#### Scenario: Notice uses cautious wording for freshness token changes
- **WHEN** a skill changes only because its freshness token differs for the same resolved skill directory
- **THEN** the notice SHALL describe that skill as having a detected skill-directory change
- **AND** the notice SHALL instruct the model to treat current skill content as superseding earlier assumptions

#### Scenario: Notice names directory switch paths
- **WHEN** a skill change is caused by a directory switch
- **THEN** the notice SHALL identify the affected skill by name
- **AND** the notice SHALL include the old resolved skill directory and the new resolved skill directory in `old -> new` form

#### Scenario: Notice is model-only and one-turn scoped
- **WHEN** the system emits a skill freshness notice for a turn
- **THEN** the notice SHALL be visible to the model for that turn only
- **AND** the system SHALL NOT expose that notice as a user-visible chat message
- **AND** the system SHALL NOT persist that notice into long-lived session memory as a recurring prompt banner

### Requirement: Applied snapshot SHALL be updated immediately after refresh handling
After the system detects associated skill changes for a turn and applies the resulting refresh and notice, it SHALL immediately persist the applied snapshot state for that turn.

#### Scenario: Changed snapshot entry is updated immediately
- **WHEN** the current turn detects a freshness token change for an associated skill
- **THEN** the system SHALL update that snapshot entry to the new freshness token in the same turn after refresh handling

#### Scenario: Directory switch overwrites the stored snapshot entry
- **WHEN** the current turn detects a directory switch for an associated skill
- **THEN** the system SHALL overwrite the stored snapshot entry with the new resolved skill directory and new freshness token in the same turn after refresh handling

#### Scenario: Withdrawal removes the stored snapshot entry
- **WHEN** the current turn detects that an associated skill has been withdrawn from the effective skill set
- **THEN** the system SHALL remove that skill from the stored session snapshot in the same turn after refresh handling

#### Scenario: Applied snapshot prevents repeated notices for the same change
- **WHEN** a turn has already applied a freshness change and persisted the resulting snapshot state
- **AND** the next turn sees the same snapshot values and effective skill resolution
- **THEN** the system SHALL NOT emit another freshness notice for that same prior change
