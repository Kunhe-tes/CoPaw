## ADDED Requirements

### Requirement: Chat content-only presentation is URL driven

The Console SHALL activate chat content-only presentation only for a concrete `/chat/{chat.id}` route whose parsed `showContentOnly` query value is exactly the lower-case string `true`. Activation SHALL NOT depend on iframe presence or request `source`, SHALL NOT require a new `USER_DATA` field, and SHALL NOT persist presentation state outside the URL.

#### Scenario: Embedded host opens a content-only chat

- **WHEN** an embedded host opens `/chat/{chat.id}?showContentOnly=true`
- **THEN** the Console applies content-only presentation on the first render

#### Scenario: User opens the same URL directly

- **WHEN** a user opens `/chat/{chat.id}?showContentOnly=true` in a top-level browser
- **THEN** the Console applies the same presentation using the normal authenticated chat route

#### Scenario: Parameter is absent, invalid, or lacks a target

- **WHEN** `showContentOnly` is absent, has any value other than the exact lower-case string `true`, appears on a non-chat route, or appears on `/chat` without a concrete target ID
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

### Requirement: Existing chat behavior is inherited without content-only branches

Content-only presentation SHALL use the normal `/chat/{chat.id}` identity, session, loading, empty, error, request, stream, reconnect, cancellation, background-effect, and preview-recording behavior. The presentation flag SHALL NOT be used by session providers, runtime controllers, request ownership, response cards, approval/feedback handlers, or preview telemetry policy.

#### Scenario: Existing chat is restored

- **WHEN** a content-only URL targets a chat that normal `/chat/{chat.id}` can restore
- **THEN** the same title, messages, state, and message actions are rendered through the existing providers and controllers

#### Scenario: Running chat continues to stream

- **WHEN** the routed chat is already running and the normal route reconnects to its SSE output
- **THEN** content-only presentation displays subsequent streamed output and completion through that same existing path

#### Scenario: Normal chat compatibility

- **WHEN** the user opens a chat without active content-only presentation
- **THEN** global navigation, `ChatSidebar`, generated files, model selection, composer, uploads, session behavior, message operations, and streaming retain their existing behavior

#### Scenario: Existing embedding compatibility

- **WHEN** an existing host uses `hideMenu` or `origin=Y` without active content-only presentation
- **THEN** its current shell, identity, session, and chat behavior remain unchanged
