# chat-content-only-mode Specification

## Purpose

Define the URL-activated, runtime presentation-only chat mode that focuses a concrete conversation while preserving the normal chat route's loading, streaming, and message interactions.

## Requirements

### Requirement: Chat content-only presentation is initialized from the startup URL

The Console SHALL initialize chat content-only presentation only when a full page starts on a concrete `/chat/{chat.id}` route whose parsed `showContentOnly` query value is exactly the lower-case string `true`. Activation SHALL NOT depend on iframe presence or request `source` and SHALL NOT require a new `USER_DATA` field. Layout consumers SHALL read the initialized global flag directly without re-evaluating the current URL or `chat.id`. The flag SHALL remain active for the whole current page runtime, SHALL NOT be written to persistent browser storage, and SHALL be reset from the current URL on the next full-page startup.

#### Scenario: Embedded host opens a content-only chat

- **WHEN** an embedded host opens `/chat/{chat.id}?showContentOnly=true`
- **THEN** the Console applies content-only presentation on the first render

#### Scenario: User opens the same URL directly

- **WHEN** a user opens `/chat/{chat.id}?showContentOnly=true` in a top-level browser
- **THEN** the Console applies the same presentation using the normal authenticated chat route

#### Scenario: Internal chat navigation replaces the query string

- **WHEN** an initialized content-only chat resolves or replaces its routed chat ID and the resulting internal URL no longer contains `showContentOnly`
- **THEN** content-only presentation remains active for the rest of the current page runtime

#### Scenario: A new startup does not opt in

- **WHEN** a new full-page startup opens a URL without the exact lower-case `showContentOnly=true` value
- **THEN** the runtime presentation flag is initialized as inactive even if a previous page runtime used content-only presentation

#### Scenario: Parameter is absent, invalid, or lacks a target

- **WHEN** a full page starts with `showContentOnly` absent, with any value other than the exact lower-case string `true`, on a non-chat route, or on `/chat` without a concrete target ID
- **THEN** the parameter does not change that route's normal layout or behavior

### Requirement: Content-only presentation hides only the requested workspace surfaces

Content-only presentation SHALL omit the global Header and Sidebar, the entire Conversation Workspace `ChatSidebar`, the generated-files entry/list, the model selector, the question composer, and drag/paste/upload surfaces. It SHALL retain the existing chat title and complete conversation content.

#### Scenario: Focused conversation renders

- **WHEN** content-only presentation is active
- **THEN** no global navigation, chat task/history sidebar, collapsed chat toolbar, generated-files entry/list, model selector, question composer, attachment action, speech action, drag-upload overlay, or paste-file input surface is rendered
- **AND** the existing title and conversation messages remain visible
- **AND** the conversation uses the available width without a reserved sidebar rail

#### Scenario: Message files remain usable

- **WHEN** a message contains downloadable or previewable files
- **THEN** those message-level file controls continue to follow their normal chat behavior
- **AND** only the independent generated-files entry/list is hidden

### Requirement: Existing message interactions remain unchanged

Content-only presentation SHALL NOT change message-card visibility, permissions, state checks, event handlers, or mutation behavior. Any message-level interaction that normal `/chat/{chat.id}` would expose SHALL remain governed by the same existing logic.

#### Scenario: Approval and feedback remain interactive

- **WHEN** normal chat rules expose approval/deny or response-feedback controls for a loaded or streamed message
- **THEN** the same controls and handlers remain available in content-only presentation

#### Scenario: Retry, suggestions, and message affordances remain interactive

- **WHEN** normal chat rules expose retry/regenerate, suggestions, copy, download, preview, disclosure, or quick-navigation controls
- **THEN** content-only presentation preserves the same visibility and behavior

### Requirement: Existing chat behavior is inherited with a focused missing-chat exception

Content-only presentation SHALL use the normal `/chat/{chat.id}` identity, session, loading, empty, request, stream, reconnect, cancellation, background-effect, and preview-recording behavior. The presentation flag SHALL NOT be used by request ownership, response cards, approval/feedback handlers, or preview telemetry policy. The only content-only-specific session error branch SHALL be a non-interactive unavailable result when the active chat detail request returns HTTP 404.

#### Scenario: Existing chat is restored

- **WHEN** a content-only URL targets a chat that normal `/chat/{chat.id}` can restore
- **THEN** the same title, messages, state, and message actions are rendered through the existing providers and controllers

#### Scenario: Missing chat renders an unavailable result

- **WHEN** the active content-only chat detail request returns HTTP 404
- **THEN** the Console displays a centered 404 result explaining that the conversation does not exist or has been deleted
- **AND** the Console does not display the Welcome question-entry surface

#### Scenario: Valid empty chat is not missing

- **WHEN** the active content-only chat detail request succeeds with no conversation messages
- **THEN** the Console retains the existing content-only empty presentation
- **AND** the Console does not display the 404 result

#### Scenario: Stale missing-chat response is ignored

- **WHEN** a chat detail request returns HTTP 404 after the active session has changed
- **THEN** the stale response does not replace the current session with the 404 result

#### Scenario: Running chat continues to stream

- **WHEN** the routed chat is already running and the normal route reconnects to its SSE output
- **THEN** content-only presentation displays subsequent streamed output and completion through that same existing path

#### Scenario: Normal chat compatibility

- **WHEN** the user opens a chat without active content-only presentation
- **THEN** global navigation, `ChatSidebar`, generated files, model selection, composer, uploads, session behavior, message operations, and streaming retain their existing behavior

#### Scenario: Existing embedding compatibility

- **WHEN** an existing host uses `hideMenu` or `origin=Y` without active content-only presentation
- **THEN** its current shell, identity, session, and chat behavior remain unchanged
