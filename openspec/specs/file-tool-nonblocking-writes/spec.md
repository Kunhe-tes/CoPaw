# file-tool-nonblocking-writes Specification

## Purpose
TBD - created by archiving change async-file-io-tool-writes. Update Purpose after archive.
## Requirements
### Requirement: File tool writes SHALL avoid blocking the event loop
The system SHALL execute the filesystem write phase of `write_file` and
`append_file` without blocking unrelated event-loop work.

#### Scenario: Slow write does not stall unrelated async work
- **WHEN** `write_file` performs a slow filesystem write
- **THEN** unrelated event-loop tasks SHALL remain able to make progress while
  the write is in flight

#### Scenario: Append write uses the same non-blocking write path
- **WHEN** `append_file` persists its merged content to disk
- **THEN** the filesystem write phase SHALL use the shared non-blocking write
  path
- **AND** the tool SHALL retain its existing async interface

### Requirement: File tool writes SHALL preserve atomic target replacement
The system SHALL keep the existing temp-file replacement behavior for
`write_file` and `append_file` while offloading the write phase.

#### Scenario: Completed write replaces target atomically
- **WHEN** `write_file` or `append_file` completes successfully
- **THEN** the tool SHALL write the full content to a temp file in the target
  directory
- **AND** it SHALL replace the target file only after the temp-file write
  succeeds

#### Scenario: Same-path writes remain serialized
- **WHEN** concurrent tool calls write to the same resolved file path
- **THEN** the system SHALL preserve the existing per-path lock behavior
- **AND** the writes SHALL not overlap their complete atomic replacement flow

### Requirement: File tool write cancellation SHALL preserve current safety
The system SHALL preserve the current cancellation behavior that avoids leaving
partially updated target files behind.

#### Scenario: Cancelled overwrite leaves target unchanged
- **WHEN** a `write_file` call is cancelled after its temp-file write has begun
  but before target replacement completes
- **THEN** the original target file SHALL remain unchanged
- **AND** any temp file created for the cancelled write SHALL be cleaned up

#### Scenario: Cancelled append leaves target unchanged
- **WHEN** an `append_file` call is cancelled after its temp-file write has
  begun but before target replacement completes
- **THEN** the original target file SHALL remain unchanged
- **AND** any temp file created for the cancelled append SHALL be cleaned up

