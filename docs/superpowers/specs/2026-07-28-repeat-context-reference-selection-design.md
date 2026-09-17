# Repeated Context Reference Selection

## Goal

Allow a Console user to select the same `@` context reference more than once in
one composer message, while retaining exactly one system-prompt directive for
that reference on the backend.

## Design

The composer will no longer reject selection when the selected-reference list
already has the same `id`. Each selection will continue to replace the active
`@` query with its display text and append the selected reference to the
one-turn `context_references` request array. This permits repeated visible
mentions and preserves their positions in the user message.

The runner will retain its existing `(type, id)` de-duplication before building
context-reference directives. Consequently a repeated skill, MCP tool, or
workspace file may appear repeatedly in the user message and request payload,
but contributes one directive to the system prompt for that turn.

## Scope and Safety

No change is made to MCP registration, skill loading, file access rules, or
backend reference validation. Existing limits and path/server/skill
revalidation remain in effect.

## Tests

Add a frontend regression test that selects the same reference twice and
asserts two visible mentions and two selected entries. Keep the existing runner
test that establishes deduplicated directive rendering, extending it only if
needed to make the one-directive invariant explicit.
