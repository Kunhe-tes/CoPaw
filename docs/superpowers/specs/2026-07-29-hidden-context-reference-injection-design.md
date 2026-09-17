# Hidden context-reference injection design

## Goal

When a Console user selects MCP tools, skills, or workspace files, append the
trusted directives to that turn's user message instead of adding them to the
system prompt. The model must retain the directives in persisted chat history,
but Console must never receive or render them.

## Data flow

1. The Console continues to submit structured `context_references` and
   `selected_skill_names`; the server validates and resolves them into trusted
   directives.
2. The runner renders those directives as one delimited internal suffix and
   appends it after the user's current text for the active turn.
3. The persisted user message stores the complete model-facing text and
   metadata identifying the suffix boundary. Subsequent turns therefore retain
   the original selection context when the model reads the chat history.
4. Chat-history API responses remove the marked suffix before returning a
   message to Console. The frontend receives and renders only the text the user
   entered, not the internal directives.

## Boundaries

- Source- and request-level `system_prompt_injections` remain system-prompt
  behavior. This change only moves directives derived from explicit Console
  selections: skills, MCP tools, and workspace files.
- Directive validation and rendering remain server-side; the browser never
  sends directive text.
- A delimiter and metadata must be unambiguous, versioned/namespace-scoped,
  and safe to remove only when the stored content matches the recorded suffix.
- Chat history stored on disk remains an audit/replay source and includes the
  full model-facing message plus its metadata.

## API and UI behavior

The Chat history API returns a display-safe copy of marked messages: it retains
the message identity, role, timestamps, and other metadata needed by Console,
but replaces its content with the original visible user text. The raw stored
message is not returned through this endpoint. Existing unmarked messages and
non-Console consumers keep their current behavior.

## Error handling

- If no valid directive is resolved, do not add a suffix or metadata.
- If metadata is absent, malformed, or inconsistent with the stored content,
  fail closed for UI safety: do not expose a candidate injected block.
- Invalid client references continue to be ignored by the existing trusted
  resolver and cannot create hidden content.

## Tests

- Unit test the composition helper: no directives leaves text unchanged;
  directives are appended in existing deterministic order; metadata can restore
  the display text.
- Unit test history serialization/API filtering: persisted data keeps the full
  message while the Console response excludes the suffix.
- Regression-test the runner so selected skills, MCP tools, and workspace files
  no longer appear in the system prompt and are supplied through the active
  user turn instead.
- Add a Console-session conversion test confirming a restored history displays
  only the original input.
