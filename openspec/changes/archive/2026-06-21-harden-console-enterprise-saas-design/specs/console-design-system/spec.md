## MODIFIED Requirements

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
