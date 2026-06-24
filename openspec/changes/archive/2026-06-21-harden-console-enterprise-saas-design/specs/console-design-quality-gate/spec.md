## MODIFIED Requirements

### Requirement: Impeccable-assisted Console review

The Console design workflow SHALL use Impeccable as an optional quality review and detector layer for AI-assisted UI work while preserving `console/DESIGN.md` as the project design authority and `PRODUCT.md` as strategic product context.

#### Scenario: Impeccable reviews a Console UI change

- **WHEN** Impeccable commands, detector output, or hooks review a new or modified user-visible Console surface
- **THEN** their findings SHALL be treated as review input that must be reconciled against `console/DESIGN.md`, not as an automatic replacement for documented CoPaw design rules

#### Scenario: Impeccable conflicts with documented CoPaw rules

- **WHEN** an Impeccable finding conflicts with an intentional rule in `console/DESIGN.md`
- **THEN** the documented CoPaw rule SHALL prevail unless a separate approved design-system change updates `console/DESIGN.md`

#### Scenario: Impeccable requires product context

- **WHEN** the local Impeccable skill requires project context before running a review command
- **THEN** the repository SHALL satisfy that requirement through strategic `PRODUCT.md` context without running `/impeccable init` or committing a competing root visual `DESIGN.md`
