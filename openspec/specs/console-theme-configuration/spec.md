# console-theme-configuration Specification

## Purpose
TBD - created by archiving change adopt-embedded-blue-gray-theme. Update Purpose after archive.
## Requirements
### Requirement: Typed management theme authority

The Console SHALL maintain one typed management-theme token object as the authoritative editable source for management canvas, surface, subtle-surface, navigation, border, text, primary, primary-hover, and primary-soft color roles.

#### Scenario: A later palette adjustment is requested

- **WHEN** a developer changes an approved management color role
- **THEN** the developer SHALL be able to update the value in the typed token configuration without editing individual page selectors

### Requirement: Runtime CSS variable bridge

The Console SHALL expose the typed management-theme roles as stable CSS custom properties for Less/CSS consumers during application startup.

#### Scenario: Management UI renders

- **WHEN** the application initializes a management surface
- **THEN** its semantic CSS variables SHALL reflect the values from the typed management-theme configuration

### Requirement: Semantic palette consumption

Calibrated management surfaces SHALL consume semantic theme roles instead of duplicating the configured white-first embedded palette as page-specific literals.

#### Scenario: A calibrated component needs a primary or surface color

- **WHEN** Header/navigation, `/models`, or a related management dialog renders the color
- **THEN** it SHALL obtain the color through the management token or CSS variable role appropriate to that purpose

