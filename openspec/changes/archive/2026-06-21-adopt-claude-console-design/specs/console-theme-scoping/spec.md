## ADDED Requirements

### Requirement: Layered Console theme roles

The Console SHALL define reusable base roles, a CoPaw Management Console theme, and an independent Conversation Workspace theme rather than using page-specific colors as the design-system interface.

#### Scenario: A future non-conversation page is migrated

- **WHEN** a later change applies the Management Console theme to a non-conversation surface
- **THEN** the page SHALL be able to consume shared semantic color, typography, spacing, radius, elevation, and interaction roles without depending on `/models` styles

#### Scenario: Shared foundation changes

- **WHEN** a base spacing, radius, motion, accessibility, or semantic-state role changes
- **THEN** Management and Conversation scopes SHALL be able to consume the shared role without forcing their brand colors or typography to become identical

### Requirement: Conversation Workspace isolation

The CoPaw Management Console theme SHALL NOT change the Conversation Workspace's existing `#3769FC` emphasis, typography, content surfaces, independent conversation sidebar, composer, or conversation-specific presentation during this change.

#### Scenario: Chat renders beside global navigation

- **WHEN** the standalone shell displays global navigation beside the Conversation Workspace
- **THEN** the global navigation SHALL use the Management theme while the chat content region and conversation sidebar retain their existing Conversation theme

#### Scenario: Management font declarations are loaded

- **WHEN** local management fonts are available in the application bundle
- **THEN** the Conversation Workspace SHALL NOT adopt those font roles unless a later approved chat migration explicitly applies them

### Requirement: Scoped management adoption

The Management Console theme SHALL be applied through an explicit reusable scope and SHALL NOT rely on a global body-font or global primary-color replacement that unintentionally migrates chat or untouched legacy pages.

#### Scenario: An untouched legacy page renders

- **WHEN** a non-conversation legacy page has not yet been migrated
- **THEN** the new theme infrastructure SHALL NOT force a complete visual migration as a side effect of this change

#### Scenario: Embedded management page renders

- **WHEN** a migrated management page renders with `hideMenu=true`
- **THEN** its management theme SHALL remain available without requiring the global Header or Sidebar
