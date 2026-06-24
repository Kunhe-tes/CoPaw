## ADDED Requirements

### Requirement: Session filesystem writes SHALL be offloaded
The system SHALL execute every `SafeJSONSession` JSON filesystem write outside
the event-loop thread while preserving the existing async persistence APIs and
persisted JSON structure.

#### Scenario: Session state save does not block the event loop
- **WHEN** a session state save performs a slow filesystem write
- **THEN** unrelated event-loop tasks SHALL remain able to run while the write is in progress

#### Scenario: All session write entry points use the offloaded write path
- **WHEN** session state is written by a state save, key update, skill snapshot save, or merged-state save
- **THEN** the filesystem write SHALL execute through the shared offloaded write path
- **AND** the resulting JSON document SHALL retain the existing structure and Unicode behavior

### Requirement: Session writes SHALL be coordinated per path
The system SHALL serialize writes that target the same effective session JSON
path with a per-path `asyncio.Lock`, and SHALL NOT serialize writes solely
because they target different session paths.

#### Scenario: Same-path writes do not overlap
- **WHEN** two async tasks write to the same effective session JSON path concurrently
- **THEN** the second task SHALL wait until the first task's complete write operation releases the path lock

#### Scenario: Different-path writes remain independent
- **WHEN** two async tasks write to different effective session JSON paths concurrently
- **THEN** each task SHALL use a different path lock
- **AND** neither task SHALL wait solely because the other session path is being written

#### Scenario: Separate session objects coordinate the same path
- **WHEN** separate `SafeJSONSession` objects in the same event loop target the same effective session JSON path
- **THEN** they SHALL use the same path lock

#### Scenario: Locks are not reused across event loops
- **WHEN** the same effective session JSON path is accessed from different event loops
- **THEN** each event loop SHALL use its own compatible path lock

### Requirement: Session read-modify-write operations SHALL preserve coordinated updates
The system SHALL hold the target path lock for the complete read-modify-write
sequence of session state updates so that same-path writers cannot derive
results concurrently from the same stale state.

#### Scenario: Concurrent top-level key updates are preserved
- **WHEN** concurrent tasks update different top-level keys in the same session state
- **THEN** the final persisted state SHALL contain both updates

#### Scenario: State-module save preserves an earlier coordinated update
- **WHEN** a state-module save and another coordinated update target the same session path concurrently
- **THEN** each operation SHALL read existing state only after acquiring the path lock
- **AND** the final persisted state SHALL preserve the merged results according to their serialized order

#### Scenario: Skill snapshot save preserves concurrent session state
- **WHEN** a session skill snapshot is saved concurrently with another coordinated session state update
- **THEN** the snapshot save SHALL update only the top-level skill snapshot key through the coordinated update path
- **AND** the final persisted state SHALL preserve the other coordinated update
