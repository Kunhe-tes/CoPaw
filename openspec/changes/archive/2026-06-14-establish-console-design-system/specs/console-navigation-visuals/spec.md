## ADDED Requirements

### Requirement: Light low-distraction global navigation
The global navigation SHALL use a light, low-distraction visual treatment that may use neutral, softly tinted, or layered light surfaces without relying on a pure-white background or large saturated-blue areas.

#### Scenario: Navigation is displayed in standalone mode
- **WHEN** `hideMenu` is false
- **THEN** menu groups, active items, icons, labels, separators, and the content boundary SHALL present a clear but visually subordinate hierarchy relative to the current page

### Requirement: Preserve navigation behavior
The navigation redesign SHALL preserve existing menu structure, labels, ordering, route mapping, visibility rules, permissions, expanded groups, and collapse behavior.

#### Scenario: User selects or expands a menu item
- **WHEN** the user performs an existing navigation interaction
- **THEN** the same route or expansion-state behavior SHALL occur after the visual redesign

#### Scenario: Navigation is hidden by the host
- **WHEN** iframe context sets `hideMenu=true`
- **THEN** the Header and global Sidebar SHALL remain hidden according to the existing shell behavior

### Requirement: Navigation collapse control presentation
The existing global navigation collapse control SHALL remain available and MAY receive updated placement and styling without changing its state semantics.

#### Scenario: User toggles navigation collapse
- **WHEN** the user activates the redesigned collapse control
- **THEN** the navigation SHALL enter the same expanded or collapsed state produced by the current control

### Requirement: Preserve themed logo configuration
The navigation and Header redesign SHALL NOT change configured logo assets, theme selection, or logo dimensions.

#### Scenario: A source-specific logo is configured
- **WHEN** the Console resolves a source-specific brand theme
- **THEN** the same configured logo asset and sizing behavior SHALL be used, while surrounding layout may adopt the new visual system

### Requirement: Consistent navigation icon presentation
Navigation icons SHALL use consistent visual size, alignment, and state color while preserving existing semantic icon choices unless replacement is required for visual consistency within the scoped redesign.

#### Scenario: Navigation items are rendered
- **WHEN** collapsed or expanded navigation items are visible
- **THEN** their icons and labels SHALL align consistently and active, hover, focus, and disabled presentation SHALL remain distinguishable
