## MODIFIED Requirements

### Requirement: Complete model-management trial scope

The `/models` redesign SHALL cover the default LLM configuration, provider management content, provider cards, search and action controls, provider/model dialogs, and all existing visual states using the CoPaw Management Console theme.

#### Scenario: User opens model management

- **WHEN** the `/models` route renders successfully
- **THEN** the default model area and provider-management area SHALL present one coherent white-first management-page hierarchy with blue primary actions and compact operational typography

#### Scenario: User opens an existing provider or model dialog

- **WHEN** an existing configuration, model-management, distribution, local-runtime, or related dialog is opened
- **THEN** the dialog SHALL use the CoPaw Management Console roles while retaining its existing fields, validation, actions, and outcomes

### Requirement: Compact identifiable provider cards

Provider cards SHALL use a compact CoPaw management-card layout and visibly retain provider icon, provider name, provider ID, availability, key connection summary including Base URL when applicable, model count, and operation access.

The compact layout SHALL use a grouped identity region, one continuous aligned summary list, restrained low-contrast boundaries, and an unfilled action row rather than multiple nested panels, heavy shadows, or oversized internal padding. The page SHALL provide one concise icon-and-breadcrumb anchor above the management content without duplicating the current page title.

#### Scenario: A remote provider card renders

- **WHEN** a remote provider is included in the filtered results
- **THEN** its identifying and operational summary SHALL be readable without opening the provider dialog and SHALL use the approved UI and technical typography roles

#### Scenario: A local provider card renders

- **WHEN** a local provider is included in the results
- **THEN** its local/runtime identity and model summary SHALL remain distinguishable within the same management card system

### Requirement: Adaptive desktop layout

The model-management page SHALL use efficient desktop gutters, the scoped Management Console theme, and a left-aligned provider-card grid with a practical maximum card width suitable for the agreed desktop viewport range and embedded host containers.

#### Scenario: Page renders at a required standalone viewport

- **WHEN** the page renders at `1280x720`, `1440x900`, or `1920x1080`
- **THEN** the content SHALL use the available width without unlimited stretching, unintended overlap, inaccessible operations, or typography-driven clipping

#### Scenario: Page renders without global navigation

- **WHEN** `hideMenu=true` removes the Header and global Sidebar
- **THEN** the model-management layout, platform font roles, and Management theme SHALL adapt to the expanded content region without changing model-management behavior
