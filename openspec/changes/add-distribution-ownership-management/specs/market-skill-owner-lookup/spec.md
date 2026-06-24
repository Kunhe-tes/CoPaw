## ADDED Requirements

### Requirement: Market skill owner lookup by name
The application market SHALL provide a manager action for each skill to look up current users who own a same-named skill.

#### Scenario: Manager opens owner lookup
- **WHEN** a manager opens the skill management action for a market skill
- **THEN** the UI offers a skill owner lookup action

#### Scenario: User owns same-named skill
- **WHEN** a source user has a received or owned skill whose stable skill name equals the market skill name
- **THEN** the lookup lists that user as owning the skill

#### Scenario: User does not own same-named skill
- **WHEN** a source user has no skill with the same stable skill name
- **THEN** the lookup does not list that user as owning the skill

### Requirement: Skill owner lookup version status
The skill owner lookup SHALL include market and user-side version information when available.

#### Scenario: User-side version is available
- **WHEN** the matched user skill has a version or received version
- **THEN** the lookup displays the user-side version alongside the market version

#### Scenario: User-side version is older
- **WHEN** the matched user skill indicates an update is available or its version differs from the market version
- **THEN** the lookup indicates that the user needs an update
