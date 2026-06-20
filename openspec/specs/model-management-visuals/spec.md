# model-management-visuals Specification

## Purpose

TBD - created by archiving change establish-console-design-system. Update Purpose after archive.

## Requirements

### Requirement: Complete model-management trial scope

The `/models` redesign SHALL cover the default LLM configuration, provider management content, provider cards, search and action controls, provider/model dialogs, and all existing visual states.

#### Scenario: User opens model management

- **WHEN** the `/models` route renders successfully
- **THEN** the default model area and provider-management area SHALL present one coherent management-page hierarchy

#### Scenario: User opens an existing provider or model dialog

- **WHEN** an existing configuration, model-management, distribution, local-runtime, or related dialog is opened
- **THEN** the dialog SHALL use the trial design system while retaining its existing fields, validation, actions, and outcomes

### Requirement: Compact identifiable provider cards

Provider cards SHALL use a compact management-card layout and visibly retain provider icon, provider name, provider ID, availability, key connection summary including Base URL when applicable, model count, and operation access.

The compact layout SHALL use a grouped identity region, one continuous aligned summary list, and an unfilled action row rather than multiple nested panels or oversized internal padding. The page SHALL provide one concise icon-and-breadcrumb anchor above the management content without duplicating the current page title.

#### Scenario: A remote provider card renders

- **WHEN** a remote provider is included in the filtered results
- **THEN** its identifying and operational summary SHALL be readable without opening the provider dialog

#### Scenario: A local provider card renders

- **WHEN** a local provider is included in the results
- **THEN** its local/runtime identity and model summary SHALL remain distinguishable within the same card system

### Requirement: Discoverable provider actions

Primary provider actions SHALL remain directly visible, while low-frequency actions MAY be grouped in a clearly discoverable more-actions control.

#### Scenario: User reviews a provider card without hovering

- **WHEN** the card is in its normal resting state
- **THEN** the user SHALL be able to identify and access its primary operations without relying on hover-only controls

### Requirement: Preserve model-management behavior

The visual redesign SHALL preserve existing model and provider requests, filtering, additions, removals, configuration, distribution, tests, downloads, runtime controls, validation, confirmations, permissions, and result handling.

#### Scenario: User performs an existing operation

- **WHEN** the user invokes an operation from its redesigned control
- **THEN** the same business handler, request semantics, confirmation requirements, and success or failure result SHALL apply

#### Scenario: Search query changes

- **WHEN** the user enters a provider search query
- **THEN** the existing filtering behavior SHALL produce the same matching provider set

### Requirement: Unified asynchronous and exceptional states

The model-management page SHALL provide consistent design-system presentation for loading, empty, error, disabled, and in-progress states without changing their activation conditions or recovery behavior.

#### Scenario: Provider data is loading

- **WHEN** the existing loading condition is active
- **THEN** the page SHALL show the documented loading presentation without enabling unavailable operations

#### Scenario: Loading fails

- **WHEN** the existing error condition is active
- **THEN** the page SHALL show the documented error presentation and preserve the existing retry behavior

#### Scenario: An operation is disabled or in progress

- **WHEN** existing state or permission logic disables an operation or marks it in progress
- **THEN** its visual state SHALL be clear and the underlying enablement rule SHALL remain unchanged

### Requirement: Adaptive desktop layout

The model-management page SHALL use efficient desktop gutters and a left-aligned provider-card grid with a practical maximum card width suitable for the agreed desktop viewport range and embedded host containers.

#### Scenario: Page renders at a required standalone viewport

- **WHEN** the page renders at `1280x720`, `1440x900`, or `1920x1080`
- **THEN** the content SHALL use the available width without unlimited stretching, unintended overlap, or inaccessible operations

#### Scenario: Page renders without global navigation

- **WHEN** `hideMenu=true` removes the Header and global Sidebar
- **THEN** the model-management layout SHALL adapt to the expanded content region without changing model-management behavior

### Requirement: Presentation copy integrity

The redesign SHALL preserve current menu, field, button, and help-text semantics while correcting unambiguous localization-key leakage within the scoped page.

#### Scenario: A translation key is missing from visible presentation

- **WHEN** the current UI would display a raw localization key such as an unresolved action label
- **THEN** the redesigned page SHALL display the intended localized text without changing the business action it represents

### Requirement: Embedded blue-gray model-management palette

The `/models` page and its related dialogs SHALL use the configured white-first management canvas, white item surfaces, near-white functional panels, neutral borders/text, and `#3769FC` primary actions while retaining the accepted layout, density, radii, and adaptive card behavior.

#### Scenario: Default model panel renders

- **WHEN** the default LLM configuration is displayed
- **THEN** its panel, fields, disabled states, focus states, save action, and distribution action SHALL use semantic near-white and neutral management roles without warm cream, coral, or heavy blue-gray presentation

#### Scenario: Provider management renders

- **WHEN** provider cards, search, page actions, status, or operation controls are displayed
- **THEN** white item surfaces SHALL be separated from the white-first canvas by semantic borders and primary actions SHALL use the configured blue role

#### Scenario: A related dialog opens

- **WHEN** a provider, model, distribution, confirmation, result, or runtime dialog is shown
- **THEN** its surface, border, focus, primary action, disabled state, and notices SHALL remain visually coherent with the white-first management theme

#### Scenario: A management select dropdown opens

- **WHEN** a provider, model, or related management select dropdown is shown
- **THEN** its elevated panel SHALL use a white surface, unselected hover options SHALL use the near-white subtle surface, and selected options SHALL use the configured primary-soft background rather than a neutral gray fill
