## MODIFIED Requirements

### Requirement: Light low-distraction global navigation

The global navigation SHALL use the configured light blue-gray Management Console palette with a neutral navigation surface, blue-gray text/icon hierarchy, and `#3769FC`-based active, hover, and focus emphasis without warm cream, coral, or large saturated-blue areas.

#### Scenario: Navigation is displayed beside embedded content

- **WHEN** `hideMenu` is false and the global navigation is visible
- **THEN** menu groups, active items, icons, labels, separators, and the content boundary SHALL present a clear but visually subordinate hierarchy relative to the current page using semantic management-theme roles

#### Scenario: Navigation is hidden by the host

- **WHEN** iframe context sets `hideMenu=true`
- **THEN** the Header and global Sidebar SHALL remain hidden and the embedded content SHALL retain the blue-gray management canvas without exposed shell gaps
