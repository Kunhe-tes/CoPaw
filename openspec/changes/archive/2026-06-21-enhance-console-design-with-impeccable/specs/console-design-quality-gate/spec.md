## ADDED Requirements

### Requirement: Impeccable-assisted Console review

The Console design workflow SHALL use Impeccable as an optional quality review and detector layer for AI-assisted UI work while preserving `console/DESIGN.md` as the project design authority.

#### Scenario: Impeccable reviews a Console UI change

- **WHEN** Impeccable commands, detector output, or hooks review a new or modified user-visible Console surface
- **THEN** their findings SHALL be treated as review input that must be reconciled against `console/DESIGN.md`, not as an automatic replacement for documented CoPaw design rules

#### Scenario: Impeccable conflicts with documented CoPaw rules

- **WHEN** an Impeccable finding conflicts with an intentional rule in `console/DESIGN.md`
- **THEN** the documented CoPaw rule SHALL prevail unless a separate approved design-system change updates `console/DESIGN.md`

### Requirement: Safe Impeccable command boundary

The Console design workflow SHALL document which Impeccable commands are safe for routine review and which commands require explicit caution because they can alter design context or product identity.

#### Scenario: Routine Console UI review

- **WHEN** an AI assistant is reviewing or polishing a Console UI change
- **THEN** it MAY use Impeccable review commands such as audit, critique, polish, layout, typeset, or harden to identify quality issues within the accepted CoPaw design direction

#### Scenario: Context-generating command is considered

- **WHEN** an AI assistant considers using an Impeccable command that generates or rewrites product/design context, such as init or document
- **THEN** it SHALL NOT commit a competing `DESIGN.md` or product manual unless an approved design-system change explicitly permits that authority change

#### Scenario: Identity-shifting command is considered

- **WHEN** an AI assistant considers using an Impeccable command that can change palette, typography, motion, or product identity, such as colorize, bolder, delight, animate, or overdrive
- **THEN** it SHALL treat the output as exploratory unless the user has approved the specific visual direction through the repository workflow

### Requirement: Detector calibration

The project SHALL calibrate Impeccable detector configuration against CoPaw's intentional design choices before making detector output a required gate.

#### Scenario: Detector configuration is added

- **WHEN** `.impeccable/config.json` or equivalent detector configuration is committed
- **THEN** it SHALL preserve documented CoPaw decisions such as platform font stacks, white-first embedded management surfaces, neutral text roles, compact operational density, and the fixed `#3769FC` Conversation Workspace emphasis where applicable

#### Scenario: Detector findings are sampled

- **WHEN** the detector is run against representative Console surfaces
- **THEN** recurring findings that are intentional CoPaw choices SHALL be either documented in `console/DESIGN.md` or encoded as narrow detector configuration rather than ignored informally

### Requirement: Optional hook adoption

Automatic Impeccable hooks SHALL remain optional until the repository owner explicitly accepts the hook files and approval workflow.

#### Scenario: Codex hook installation is proposed

- **WHEN** a change proposes adding `.codex/hooks.json`, `.agents/skills/impeccable`, or other Impeccable hook assets
- **THEN** the proposal SHALL identify the files added, explain that Codex hook approval is required, and include a rollback path

#### Scenario: Hook is not installed

- **WHEN** no automatic Impeccable hook is installed
- **THEN** AI assistants MAY still use documented manual detector or review commands during Console UI work when the skill is available
