## MODIFIED Requirements

### Requirement: Embedding-first blue-gray management palette

The Management Console design system SHALL use a white-first embedded palette centered on `#3769FC` and SHALL treat visual integration with white host products as its current color target.

#### Scenario: A migrated management surface renders

- **WHEN** a management surface covered by the design system is displayed
- **THEN** it SHALL use the documented white canvas, white operational surfaces, near-white subtle surfaces, neutral border/text hierarchy, and blue primary-action roles without warm cream, coral, or large blue-gray canvas roles

#### Scenario: Claude is used as a design reference

- **WHEN** a future UI change consults Claude design guidance
- **THEN** it SHALL treat Claude as a reference for restraint, hierarchy, spacing, boundaries, and radii rather than as the mandatory color palette

### Requirement: Configurable palette workflow

The design authority SHALL document the semantic color roles, their configured values, and the supported workflow for later direct palette adjustment.

#### Scenario: The embedded host fit is recalibrated

- **WHEN** the approved management palette needs another adjustment
- **THEN** the implementation SHALL preserve semantic role names and update the central token configuration, documentation, and visual verification together
