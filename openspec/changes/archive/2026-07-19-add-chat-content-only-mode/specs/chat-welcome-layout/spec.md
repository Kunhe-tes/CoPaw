## ADDED Requirements

### Requirement: Content-only presentation SHALL hide question-entry surfaces

When content-only presentation is active, the Console SHALL NOT render the normal question composer or its attachment, speech, send, drag-upload, or paste-file surfaces. This visual suppression SHALL NOT change how the existing chat route chooses or loads its welcome, loading, empty, error, message, or streaming state.

#### Scenario: Existing route reaches a welcome or empty surface

- **WHEN** the existing chat state renders without conversation messages while content-only presentation is active
- **THEN** no question composer, attachment action, speech action, send action, drag-upload overlay, or paste-file input surface is available
- **AND** no content-only-specific loading, empty, error, or session behavior replaces the existing route behavior

#### Scenario: Preserve the normal welcome experience

- **WHEN** content-only presentation is not active and normal chat has no messages
- **THEN** the existing welcome greeting, input, tabs, cases, attachment, speech, send, and new-topic behavior remain unchanged
