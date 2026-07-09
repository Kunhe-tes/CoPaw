# html-preview-event-recording Specification

## Purpose

Define when HTML preview click and list snapshot events are recorded or suppressed across normal chat, task auto-preview, Markdown/tool file cards, and operations read-only conversation replay.

## Requirements

### Requirement: Record events for active user preview sessions

The system SHALL record HTML preview click events and eligible list snapshot events when a user opens auto-preview HTML through normal chat, task output, Markdown file links, or tool-rendered file cards outside an explicitly read-only replay context.

#### Scenario: Normal chat auto-preview records button clicks

- **WHEN** a user opens an auto-preview HTML file from the normal chat page and clicks a "查看方案" control inside the preview
- **THEN** the system records an HTML preview click event classified as a plan click

#### Scenario: Task auto-preview records task-associated events

- **WHEN** a scheduled task auto-preview HTML file is opened from the normal chat task flow
- **THEN** the system records eligible click and list snapshot events with the task tracking context preserved

#### Scenario: Markdown and tool file cards keep recording

- **WHEN** an auto-preview HTML file is opened through a Markdown file link or a tool-rendered file card outside read-only replay
- **THEN** the system records eligible HTML preview events using the existing recording API

### Requirement: Suppress events for operations read-only replay

The system SHALL NOT record HTML preview click events or list snapshot events for auto-preview HTML opened from the business overview user detail read-only session replay.

#### Scenario: Read-only replay suppresses plan clicks

- **WHEN** an operations user opens another user's read-only conversation from the business overview user detail modal and clicks a "查看方案" control inside an auto-preview HTML preview
- **THEN** the system does not call the HTML preview click recording API

#### Scenario: Read-only replay suppresses list snapshots

- **WHEN** an operations user opens an auto-preview HTML list from the business overview user detail read-only session replay
- **THEN** the system does not call the HTML preview list snapshot recording API

#### Scenario: Nested read-only previews remain suppressed

- **WHEN** an operations user opens a nested preview from an auto-preview HTML file inside read-only replay and clicks controls inside the nested preview
- **THEN** the system does not record click or list snapshot events for the nested preview

### Requirement: Preserve preview interactions while suppressing recording

The system SHALL preserve existing HTML preview interactions in read-only replay while suppressing analytics recording.

#### Scenario: Nested preview opens without recording

- **WHEN** an operations user clicks a nested preview link inside an auto-preview HTML file in read-only replay
- **THEN** the nested preview opens using the existing preview modal behavior
- **AND** no click or list snapshot recording API call is made for that interaction

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
