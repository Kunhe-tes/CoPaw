# console-design-system Specification

## Purpose
TBD - created by archiving change establish-console-design-system. Update Purpose after archive.
## Requirements
### Requirement: Committed Console design source of truth

The project SHALL maintain `console/DESIGN.md` as the single committed design entry point for new and modified UI under `console/`, and SHALL treat product context, external design references, and AI design tools as inputs that must be adapted into CoPaw-specific rules before becoming authoritative.

#### Scenario: AI or developer starts a Console UI change

- **WHEN** a change creates or modifies user-visible UI under `console/`
- **THEN** the change SHALL use `console/DESIGN.md` as its project design authority

#### Scenario: Product context is consulted

- **WHEN** `PRODUCT.md` informs a Console UI decision
- **THEN** it SHALL guide strategic product intent only, while visual requirements remain governed by `console/DESIGN.md`

#### Scenario: Outside examples are consulted

- **WHEN** an outside product example, archived exploration, or AI design tool informs a decision
- **THEN** `console/DESIGN.md` SHALL record the adapted CoPaw-specific principle or link without requiring a vendored external `DESIGN.md` as a second authority

#### Scenario: AI design tooling produces project context

- **WHEN** an AI design tool generates or proposes product context, design context, palette changes, typography changes, or reusable visual rules
- **THEN** the generated content SHALL remain advisory until an approved change updates `console/DESIGN.md` or the central Console design tokens

#### Scenario: Prior external-reference exploration exists

- **WHEN** a previous exploration favored a specific external visual direction
- **THEN** future Console design work SHALL evaluate that direction against CoPaw's product character, embedding needs, Chinese management density, accessibility requirements, and real surface verification rather than treating the external reference as a permanent style mandate

#### Scenario: Prior named-style migration remains open

- **WHEN** a prior OpenSpec change describes named third-party palette, typography, or migration requirements that conflict with the accepted CoPaw-first design direction
- **THEN** the affected specs SHALL be synchronized so the prior change is archived, superseded, or amended without remaining as a competing active Console design mandate

### Requirement: Enterprise SaaS product quality bar

The Console design system SHALL define enterprise SaaS product-quality rules that prevent generic AI-generated UI patterns and preserve task-focused, durable, operational interfaces.

#### Scenario: A management page is designed

- **WHEN** a future change creates or modifies a management page
- **THEN** the page SHALL prioritize task completion, scannable hierarchy, compact operational density, stable component vocabulary, visible primary actions, and reusable page patterns over marketing-style hero sections, decorative cards, gradients, or novelty interactions

#### Scenario: Component states are specified

- **WHEN** a reusable interactive component or visible workflow state is introduced or revised
- **THEN** the design SHALL account for default, hover, focus, active, disabled, loading, empty, error, unavailable, permission-limited, and in-progress states as applicable

#### Scenario: Real product data is rendered

- **WHEN** user-visible text, tables, cards, filters, or lists render dynamic data
- **THEN** the layout SHALL handle long Chinese and English text, short or empty values, high item counts, large numbers, special characters, and narrow embedded containers without unintended clipping, overlap, layout shift, or horizontal page overflow

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

The CoPaw-first design-system migration SHALL be calibrated through visual review using the real global navigation and model-management page.

#### Scenario: First implementation round completes

- **WHEN** the updated design document, scoped themes, fonts, and trial surfaces are implemented
- **THEN** browser review results and user feedback SHALL be used to revise the single `console/DESIGN.md` and implementation together

#### Scenario: Final calibration completes

- **WHEN** the revised trial surfaces pass the second agreed review, including chat isolation and Windows font review
- **THEN** the resulting `console/DESIGN.md` SHALL be treated as the latest baseline for subsequent non-conversation page migrations

### Requirement: Embedding-first blue-gray management palette

The Management Console design system SHALL use a white-first embedded palette centered on `#3769FC` and SHALL treat visual integration with white host products as its current color target.

#### Scenario: A migrated management surface renders

- **WHEN** a management surface covered by the design system is displayed
- **THEN** it SHALL use the documented white canvas, white operational surfaces, near-white subtle surfaces, neutral border/text hierarchy, and blue primary-action roles without warm cream, coral, or large blue-gray canvas roles

#### Scenario: Outside visual guidance is used

- **WHEN** a future UI change consults outside visual guidance
- **THEN** it SHALL translate useful qualities into CoPaw-specific rules rather than treating the outside source as a mandatory color palette, typography system, or product style

### Requirement: Configurable palette workflow

The design authority SHALL document the semantic color roles, their configured values, and the supported workflow for later direct palette adjustment.

#### Scenario: The embedded host fit is recalibrated

- **WHEN** the approved management palette needs another adjustment
- **THEN** the implementation SHALL preserve semantic role names and update the central token configuration, documentation, and visual verification together

### Requirement: Content-only Conversation Workspace presentation variant

The Console design authority SHALL define a focused content-only Conversation Workspace presentation variant. The variant SHALL preserve the existing Conversation Workspace typography, title behavior, message presentation, message actions, and fixed `#3769FC` emphasis while omitting only the requested surrounding navigation and question-entry surfaces.

#### Scenario: Content-only variant is documented

- **WHEN** chat content-only presentation is introduced
- **THEN** `console/DESIGN.md` documents the durable visual contract for retained title/content/actions, omitted surrounding surfaces, and layout continuity without implementation-specific activation or test details

#### Scenario: Focused content hierarchy renders

- **WHEN** the content-only variant displays a chat
- **THEN** the existing title and conversation content are visually primary
- **AND** no global navigation, chat sidebar, generated-files entry/list, model selector, composer, or upload surface competes with the content
- **AND** no empty rail or shell-colored gap is reserved for a suppressed surface

#### Scenario: Existing message controls remain accessible

- **WHEN** normal chat rules expose approval, feedback, retry, suggestion, copy, download, preview, disclosure, or quick-navigation controls
- **THEN** the content-only variant preserves their accessible names, focus treatment, and existing behavior

#### Scenario: Required viewport verification

- **WHEN** the content-only variant is reviewed at `1280x720`, `1440x900`, and `1920x1080`, embedded and top-level where applicable
- **THEN** the title, messages, message actions, previews, and stream updates remain usable without clipping, overlap, empty shell gaps, or horizontal page overflow
