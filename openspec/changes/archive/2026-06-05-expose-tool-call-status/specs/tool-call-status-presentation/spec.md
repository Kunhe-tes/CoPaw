## ADDED Requirements

### Requirement: Live tool call messages SHALL expose running status
The backend SHALL attach Tool Call Status to each user-visible live tool call start message by adding `tool_status: "running"` to the message's `content[].data` payload.

#### Scenario: Streaming a user-visible tool call start
- **WHEN** the backend streams a user-visible tool call start message
- **THEN** the tool message data includes `tool_status: "running"`
- **AND** the tool message data does not need to include `tool_error`

#### Scenario: Streaming an MCP tool call start
- **WHEN** the backend streams a user-visible MCP tool call start message
- **THEN** the MCP tool message data uses the same `tool_status: "running"` field as other user-visible tool types

### Requirement: Live tool output messages SHALL expose terminal status
The backend SHALL attach terminal Tool Call Status to each user-visible live tool output message. Successful tool output messages SHALL include `tool_status: "success"` and `tool_error: null`; failed tool output messages SHALL include `tool_status: "failed"` and a non-empty Tool Error Summary in `tool_error`.

#### Scenario: Streaming a successful tool output
- **WHEN** the backend streams a user-visible tool output message whose result is not identified as an error
- **THEN** the tool output data includes `tool_status: "success"`
- **AND** the tool output data includes `tool_error: null`

#### Scenario: Streaming a failed tool output
- **WHEN** the backend streams a user-visible tool output message whose result is identified as a tool error
- **THEN** the tool output data includes `tool_status: "failed"`
- **AND** the tool output data includes a non-empty `tool_error` string

#### Scenario: Tool output has no extractable error text
- **WHEN** the backend identifies a user-visible tool output as failed but cannot extract a specific error message
- **THEN** the tool output data includes `tool_status: "failed"`
- **AND** the tool output data includes a generic non-empty Tool Error Summary

### Requirement: Tool Error Summary SHALL be bounded
The backend SHALL expose Tool Error Summary values as bounded user-visible summaries, not full raw diagnostic logs.

#### Scenario: Error text exceeds the maximum length
- **WHEN** a failed tool output has an error explanation longer than 500 characters
- **THEN** the backend truncates the `tool_error` value to a bounded summary no longer than 500 characters

#### Scenario: Error text is within the maximum length
- **WHEN** a failed tool output has an error explanation at or below 500 characters
- **THEN** the backend preserves that explanation as the `tool_error` value after normalization

### Requirement: Backend-silent tools SHALL remain hidden from Tool Call Status presentation
The backend SHALL NOT expose Tool Call Status for tools that are intentionally hidden from the user-visible chat stream.

#### Scenario: Streaming a backend-silent tool
- **WHEN** a tool event belongs to a backend-silent tool
- **THEN** the backend does not emit that tool event with `tool_status`
- **AND** the backend does not emit that tool event with `tool_error`

### Requirement: Chat history reads SHALL rebuild Tool Call Status presentation
The backend SHALL rebuild Tool Call Status fields for saved chat history responses from persisted tool-use and tool-result records without requiring `tool_status` or `tool_error` to be stored in agent memory.

#### Scenario: Reading history with a saved tool use
- **WHEN** the chat history API rebuilds messages from a saved user-visible tool-use record
- **THEN** the rebuilt tool call message data includes `tool_status: "running"`

#### Scenario: Reading history with a successful saved tool result
- **WHEN** the chat history API rebuilds messages from a saved user-visible tool-result record whose result is not identified as an error
- **THEN** the rebuilt tool output message data includes `tool_status: "success"`
- **AND** the rebuilt tool output message data includes `tool_error: null`

#### Scenario: Reading history with a failed saved tool result
- **WHEN** the chat history API rebuilds messages from a saved user-visible tool-result record whose result is identified as a tool error
- **THEN** the rebuilt tool output message data includes `tool_status: "failed"`
- **AND** the rebuilt tool output message data includes a non-empty `tool_error` string

### Requirement: Tool Call Status SHALL NOT change persistence or run cancellation semantics
The backend SHALL treat Tool Call Status as a presentation contract and SHALL NOT use it to represent overall run success, user stop, external cancellation, or stream disconnect.

#### Scenario: Persisting agent memory after a tool run
- **WHEN** the backend saves agent memory after a turn containing tool calls
- **THEN** the persisted agent memory does not require `tool_status` or `tool_error` fields for those tool records

#### Scenario: User stops a running chat
- **WHEN** a user stop or external cancellation interrupts a Main Agent run
- **THEN** the backend does not mark an individual tool output as `tool_status: "failed"` solely because of that stop or cancellation

#### Scenario: Stream terminates without a tool output message
- **WHEN** the stream terminates with a run-level error before a user-visible tool output message exists
- **THEN** the backend does not fabricate a terminal Tool Call Status for that individual tool invocation
