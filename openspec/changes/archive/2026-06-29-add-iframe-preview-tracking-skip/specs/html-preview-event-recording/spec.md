## ADDED Requirements

### Requirement: Suppress events from iframe preview tracking opt-out

The system SHALL suppress HTML preview click events and list snapshot events in embedded iframe chat sessions when the parent `USER_DATA.data.skipPreviewTracking` parameter is `true` or `"true"`.

#### Scenario: Iframe opt-out suppresses preview events

- **WHEN** the parent iframe application sends `USER_DATA.data.skipPreviewTracking` as `true`
- **AND** the embedded user opens an auto-preview HTML file and clicks a "查看方案" control inside the preview
- **THEN** the system does not call the HTML preview click recording API
- **AND** the system does not call the HTML preview list snapshot recording API

#### Scenario: Iframe opt-out preserves preview interactions

- **WHEN** the parent iframe application sends `USER_DATA.data.skipPreviewTracking` as `"true"`
- **AND** the embedded user clicks a nested preview link inside an auto-preview HTML file
- **THEN** the nested preview opens using the existing preview modal behavior
- **AND** no HTML preview click or list snapshot recording API call is made for that interaction

#### Scenario: Missing or false iframe opt-out keeps recording

- **WHEN** the parent iframe application omits `USER_DATA.data.skipPreviewTracking` or sends it as `false` or `"false"`
- **AND** the embedded user opens an auto-preview HTML file from normal chat or a task auto-preview flow
- **THEN** the system records eligible HTML preview click and list snapshot events using the existing recording behavior
