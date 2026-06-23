## MODIFIED Requirements

### Requirement: Committed Console design source of truth

The project SHALL maintain `console/DESIGN.md` as the single committed design entry point for new and modified UI under `console/`, and SHALL treat external design references and AI design tools as inputs that must be adapted into CoPaw-specific rules before becoming authoritative.

#### Scenario: AI or developer starts a Console UI change

- **WHEN** a change creates or modifies user-visible UI under `console/`
- **THEN** the change SHALL use `console/DESIGN.md` as its project design authority

#### Scenario: External design references are consulted

- **WHEN** Linear, Vercel, Claude, Impeccable, or another external design reference informs a decision
- **THEN** `console/DESIGN.md` SHALL record the adapted CoPaw-specific principle or link without requiring a vendored external `DESIGN.md` as a second authority

#### Scenario: AI design tooling produces project context

- **WHEN** an AI design tool generates or proposes product context, design context, palette changes, typography changes, or reusable visual rules
- **THEN** the generated content SHALL remain advisory until an approved change updates `console/DESIGN.md` or the central Console design tokens

#### Scenario: Prior external-reference exploration exists

- **WHEN** a previous exploration favored a specific external visual direction
- **THEN** future Console design work SHALL evaluate that direction against CoPaw's product character, embedding needs, Chinese management density, accessibility requirements, and real surface verification rather than treating the external reference as a permanent style mandate

#### Scenario: Prior Claude-specific migration remains open

- **WHEN** a prior OpenSpec change describes Claude-specific palette, typography, or migration requirements that conflict with the accepted CoPaw-first design direction
- **THEN** the affected specs SHALL be synchronized so the prior change is archived, superseded, or amended without remaining as a competing active Console design mandate
