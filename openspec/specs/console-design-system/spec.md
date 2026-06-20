# console-design-system Specification

## Purpose
TBD - created by archiving change establish-console-design-system. Update Purpose after archive.
## Requirements
### Requirement: Committed Console design source of truth

The project SHALL maintain `console/DESIGN.md` as the single committed design entry point for new and modified UI under `console/`.

#### Scenario: AI or developer starts a Console UI change

- **WHEN** a change creates or modifies user-visible UI under `console/`
- **THEN** the change SHALL use `console/DESIGN.md` as its project design authority

#### Scenario: External design references are consulted

- **WHEN** Linear, Vercel, Claude, or another external design reference informs a decision
- **THEN** `console/DESIGN.md` SHALL record the adapted principle or link without requiring a vendored external `DESIGN.md` as a second authority

### Requirement: Light-theme design foundation

The design system SHALL define a light-theme, system-font visual foundation for typography, color roles, surfaces, borders, spacing, radii, shadows, icons, interactions, and visual states.

#### Scenario: A redesigned surface is rendered

- **WHEN** a surface covered by the new design system is displayed
- **THEN** it SHALL use the documented light-theme roles and SHALL NOT require an external web font

#### Scenario: Dark-theme infrastructure remains present

- **WHEN** existing theme-switching code is encountered during this change
- **THEN** the implementation SHALL NOT expand dark-theme styling or delete theme functionality as part of this change

### Requirement: Conversation and management patterns

The design system SHALL define one shared foundation with distinct Conversation Workspace and Management Console patterns.

#### Scenario: A conversation UI is designed

- **WHEN** a future change modifies the chat workspace
- **THEN** it SHALL preserve `#3769FC` as the conversation emphasis and prioritize conversation/current-task content, composer, task/history lists, execution details, guidance, and global navigation in that order

#### Scenario: A management page is designed

- **WHEN** a future change modifies a configuration or operational page
- **THEN** it SHALL select the applicable standard-management, list-detail, or dashboard template and use medium-high information density

### Requirement: Incremental adoption

The design system SHALL govern all future Console UI work while allowing untouched legacy surfaces to remain unchanged until their own migration.

#### Scenario: A legacy page is outside the current change scope

- **WHEN** a legacy page is not otherwise modified by the change
- **THEN** the implementation SHALL NOT apply broad overrides solely to force that page into the new visual system

#### Scenario: A legacy page is modified later

- **WHEN** a later requirement changes a visible region of a legacy page
- **THEN** the modified region SHALL adopt the applicable rules from `console/DESIGN.md`

### Requirement: UI-only behavior boundary

Design-system adoption SHALL preserve existing APIs, state semantics, routes, permissions, iframe messages, triggers, error handling, and business-operation results unless a separate approved requirement explicitly changes them.

#### Scenario: Presentation code is reorganized

- **WHEN** tokens, Less modules, or pure presentational components are extracted
- **THEN** existing business hooks, request functions, stores, and event-handler outcomes SHALL remain behaviorally equivalent

#### Scenario: A clear presentation defect is found

- **WHEN** an untranslated key or equivalent unambiguous display defect is visible
- **THEN** it MAY be corrected without redefining the underlying business wording or operation

### Requirement: Desktop and embedded verification

Redesigned Console surfaces SHALL be verified at desktop viewport sizes `1280x720`, `1440x900`, and `1920x1080`, with embedded presentation checked when the surface supports `hideMenu=true`.

#### Scenario: Desktop viewport verification

- **WHEN** a redesigned surface is reviewed at each required viewport
- **THEN** primary content and operations SHALL remain visible and usable without unintended overlap, clipping, or horizontal overflow

#### Scenario: Embedded presentation verification

- **WHEN** the surface is rendered with `hideMenu=true`
- **THEN** it SHALL use the available host container without requiring the Header or global Sidebar

### Requirement: Two-round calibration

The first design-system implementation SHALL be calibrated through two visual review rounds using the real navigation and model-management page.

#### Scenario: First implementation round completes

- **WHEN** the initial design document and trial surfaces are implemented
- **THEN** browser review results and user feedback SHALL be used to revise the document and implementation together

#### Scenario: Final calibration completes

- **WHEN** the revised trial surfaces pass the second agreed review
- **THEN** the resulting `console/DESIGN.md` SHALL be treated as the baseline for subsequent page migrations

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

