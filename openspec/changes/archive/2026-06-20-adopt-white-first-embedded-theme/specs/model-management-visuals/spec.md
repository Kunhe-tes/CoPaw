## MODIFIED Requirements

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
