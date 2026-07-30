# Runtime Chat ID Propagation

## Goal

Expose the persistent chat UUID to tools that already receive the logical
runtime session identifier.

## Contract

The runtime invocation claims gain an optional `chat_id` value. When present,
the runtime owns the following transport keys and removes caller-supplied
values for them before injecting its own value:

- subprocess and stdio MCP environment: `SWE_CHAT_ID`
- HTTP headers: `x-swe-chat-id`
- HTTP compatibility alias: `chatid`

`SWE_SESSION_ID` remains the logical channel session ID. `SWE_CHAT_ID` is the
UUID of the corresponding `ChatSpec` record. Neither identifier replaces the
other.

## Query Lifecycle

For a query, the runner must create or reuse the chat before connecting request
MCP clients. It then uses `chat.id` for MCP transport construction and updates
the active runtime-claims context for the rest of the query. Consequently,
shell commands, stdio MCP servers, and HTTP MCP servers receive the same chat
UUID.

The session-to-chat lookup remains scoped by the existing `(session_id,
channel)` behavior. The feature does not introduce a new uniqueness constraint
or change chat persistence.

## Error Handling

If no chat manager is configured, the existing behavior continues: no chat ID
is injected, while session and trace claims remain available. Existing tool
execution and MCP connection failures retain their current handling.

## Tests

Unit coverage will prove that runtime claim construction replaces supplied
`SWE_CHAT_ID`/chat headers, stdio and shell environments receive the claim, and
HTTP MCP clients receive both canonical and compatibility headers. A runner
test will prove that the chat is resolved before MCP client construction and
that its UUID is propagated.
