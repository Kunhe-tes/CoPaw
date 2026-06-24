## MODIFIED Requirements

### Requirement: Committed Console design source of truth

The project SHALL maintain only the latest `console/DESIGN.md` as the single committed design entry point for new and modified UI under `console/` and SHALL NOT retain an old project design baseline or vendored external design document as a competing authority.

#### Scenario: AI or developer starts a Console UI change

- **WHEN** a change creates or modifies user-visible UI under `console/`
- **THEN** the change SHALL use the current `console/DESIGN.md` as its project design authority

#### Scenario: External design references are consulted

- **WHEN** Claude, Linear, Vercel, or another external design reference informs a decision
- **THEN** `console/DESIGN.md` SHALL record the adapted principle or link without requiring a copied external `DESIGN.md` as a second authority

#### Scenario: A new baseline replaces an accepted baseline

- **WHEN** an approved design-system change alters the primary visual direction
- **THEN** the project SHALL update `console/DESIGN.md` in place and rely on Git and archived OpenSpec artifacts for history rather than retaining multiple live design manuals

### Requirement: Light-theme design foundation

The design system SHALL define a light-theme, CoPaw-first foundation for non-conversation typography, color roles, surfaces, borders, spacing, radii, shadows, icons, interactions, and visual states while retaining an independent Conversation Workspace theme.

#### Scenario: A redesigned management surface is rendered

- **WHEN** a surface covered by the Management Console theme is displayed
- **THEN** it SHALL use the documented white embedded canvas, restrained borders, blue action roles, and platform management typography without requiring an external web-font service

#### Scenario: Conversation Workspace is rendered

- **WHEN** the Conversation Workspace is displayed during this migration
- **THEN** it SHALL retain its existing `#3769FC` emphasis and existing conversation typography and presentation

#### Scenario: Dark-theme infrastructure remains present

- **WHEN** existing theme-switching code is encountered during this change
- **THEN** the implementation SHALL NOT expand dark-theme styling or delete theme functionality as part of this change

### Requirement: Conversation and management patterns

The design system SHALL define one shared foundation with a CoPaw-first Management Console pattern and a visually independent Conversation Workspace pattern.

#### Scenario: A conversation UI is designed

- **WHEN** a future change modifies the chat workspace
- **THEN** it SHALL preserve `#3769FC` as the conversation emphasis unless that later approved change explicitly revises the chat identity, and it SHALL prioritize conversation/current-task content, composer, task/history lists, execution details, guidance, and global navigation in that order

#### Scenario: A management page is designed

- **WHEN** a future change modifies a configuration or operational page
- **THEN** it SHALL select the applicable standard-management, list-detail, or dashboard template, use medium-high information density, and consume the documented CoPaw Management Console roles

### Requirement: Two-round calibration

The CoPaw-first design-system migration SHALL be calibrated through visual review using the real global navigation and model-management page.

#### Scenario: First implementation round completes

- **WHEN** the updated design document, scoped themes, fonts, and trial surfaces are implemented
- **THEN** browser review results and user feedback SHALL be used to revise the single `console/DESIGN.md` and implementation together

#### Scenario: Final calibration completes

- **WHEN** the revised trial surfaces pass the second agreed review, including chat isolation and Windows font review
- **THEN** the resulting `console/DESIGN.md` SHALL be treated as the latest baseline for subsequent non-conversation page migrations
