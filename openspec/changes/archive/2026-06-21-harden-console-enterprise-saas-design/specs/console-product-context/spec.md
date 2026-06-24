## ADDED Requirements

### Requirement: Strategic product context for design tooling

The project SHALL maintain a minimal `PRODUCT.md` strategic context for Impeccable-assisted product design work without making it a competing Console visual design authority.

#### Scenario: Impeccable loads project context

- **WHEN** an AI assistant runs Impeccable as a local skill for Console design work
- **THEN** `PRODUCT.md` SHALL provide register, users, product purpose, brand personality, anti-references, principles, and accessibility context
- **AND** `console/DESIGN.md` SHALL remain the source of truth for visual UI rules under `console/`

#### Scenario: Product context conflicts with Console design rules

- **WHEN** `PRODUCT.md`, Impeccable guidance, or any external reference conflicts with `console/DESIGN.md`
- **THEN** `console/DESIGN.md` SHALL govern Console UI design unless an approved design-system change updates it

#### Scenario: Product context is updated

- **WHEN** the repository owner changes the target users, product purpose, product register, or durable design principles
- **THEN** `PRODUCT.md` MAY be updated in the same OpenSpec workflow without creating a root visual `DESIGN.md`
