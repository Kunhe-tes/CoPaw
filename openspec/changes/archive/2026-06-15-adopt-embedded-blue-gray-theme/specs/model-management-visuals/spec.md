## ADDED Requirements

### Requirement: Embedded blue-gray model-management palette

The `/models` page and its related dialogs SHALL use the configured neutral blue-gray management canvas, white surfaces, blue-gray borders/text, and `#3769FC` primary actions while retaining the accepted layout, density, radii, and adaptive card behavior.

#### Scenario: Default model panel renders

- **WHEN** the default LLM configuration is displayed
- **THEN** its panel, fields, disabled states, focus states, save action, and distribution action SHALL use semantic blue-gray management roles without warm cream or coral presentation

#### Scenario: Provider management renders

- **WHEN** provider cards, search, page actions, status, or operation controls are displayed
- **THEN** white item surfaces SHALL be separated from the light blue-gray canvas by semantic borders and primary actions SHALL use the configured blue role

#### Scenario: A related dialog opens

- **WHEN** a provider, model, distribution, confirmation, result, or runtime dialog is shown
- **THEN** its surface, border, focus, primary action, disabled state, and notices SHALL remain visually coherent with the blue-gray management theme
