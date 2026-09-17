## MODIFIED Requirements

### Requirement: Content-only presentation SHALL hide question-entry surfaces

When content-only presentation is active, the Console SHALL NOT render the normal question composer or its attachment, speech, send, drag-upload, or paste-file surfaces. This visual suppression SHALL preserve how the existing chat route chooses and loads its welcome, loading, empty, message, and streaming states. When the active chat detail request returns HTTP 404, the content-only surface SHALL replace the otherwise blank empty region with the defined unavailable result.

#### Scenario: Existing route reaches a valid empty surface

- **WHEN** the existing chat state successfully loads without conversation messages while content-only presentation is active
- **THEN** no question composer, attachment action, speech action, send action, drag-upload overlay, or paste-file input surface is available
- **AND** no 404 result is displayed

#### Scenario: Missing content-only chat does not show Welcome

- **WHEN** the active content-only chat detail request returns HTTP 404
- **THEN** the unavailable result is displayed instead of the Welcome surface
- **AND** no question-entry or upload surface is mounted

#### Scenario: Preserve the normal welcome experience

- **WHEN** content-only presentation is not active and normal chat has no messages
- **THEN** the existing welcome greeting, input, tabs, cases, attachment, speech, send, and new-topic behavior remain unchanged
