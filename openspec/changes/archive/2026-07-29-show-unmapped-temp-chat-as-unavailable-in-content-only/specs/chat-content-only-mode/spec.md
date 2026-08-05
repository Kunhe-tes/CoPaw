## MODIFIED Requirements

### Requirement: Existing chat behavior is inherited with a focused missing-chat exception

Content-only presentation SHALL use the normal `/chat/{chat.id}` identity, session, loading, empty, request, stream, reconnect, cancellation, background-effect, and preview-recording behavior except when its fixed route target is a temporary local session ID that has no persisted chat mapping. The presentation flag SHALL NOT be used by request ownership, response cards, approval/feedback handlers, or preview telemetry policy. The only content-only-specific session error branch SHALL be a non-interactive unavailable result when the active chat detail request returns HTTP 404 or when the fixed route target is an unmapped temporary local session ID.

#### Scenario: Existing chat is restored

- **WHEN** a content-only URL targets a chat that normal `/chat/{chat.id}` can restore
- **THEN** the same title, messages, state, and message actions are rendered through the existing providers and controllers

#### Scenario: Missing persisted chat renders an unavailable result

- **WHEN** the active content-only chat detail request returns HTTP 404
- **THEN** the Console displays a centered 404 result explaining that the conversation does not exist or has been deleted
- **AND** the Console does not display the Welcome question-entry surface

#### Scenario: Unmapped temporary deep link renders an unavailable result without a request

- **WHEN** content-only presentation starts on a temporary local session ID that has no persisted chat mapping
- **THEN** the Console displays the same centered unavailable result
- **AND** the Console SHALL NOT request chat detail using the temporary local session ID
- **AND** the Console SHALL NOT create or restore a new empty local conversation for that route

#### Scenario: Mapped temporary deep link restores the persisted chat

- **WHEN** content-only presentation starts on a temporary local session ID that maps to a persisted chat in the session list
- **THEN** the Console resolves and restores the persisted `chat.id` through the existing session-selection path
- **AND** the Console does not display the unavailable result

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
- **THEN** global navigation, `ChatSidebar`, generated files, model selection, composer, uploads, temporary-session creation, session behavior, message operations, and streaming retain their existing behavior

#### Scenario: Existing embedding compatibility

- **WHEN** an existing host uses `hideMenu` or `origin=Y` without active content-only presentation
- **THEN** its current shell, identity, session, and chat behavior remain unchanged
