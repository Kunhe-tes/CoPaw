## MODIFIED Requirements

### Requirement: Live tool output messages SHALL expose terminal status
The backend SHALL attach terminal Tool Call Status to each user-visible live tool output message. Successful tool output messages SHALL include `tool_status: "success"` and `tool_error: null`; failed tool output messages SHALL include `tool_status: "failed"` and a non-empty Tool Error Summary in `tool_error`. Structured failed `tool_result` payloads SHALL be treated as the canonical signal for failure, while plain-text failure detection remains a backward-compatible fallback during migration.

#### Scenario: Streaming a successful tool output
- **WHEN** the backend streams a user-visible tool output message whose result is not identified as an error
- **THEN** the tool output data includes `tool_status: "success"`
- **AND** the tool output data includes `tool_error: null`

#### Scenario: Streaming a failed structured tool output
- **WHEN** the backend streams a user-visible tool output message whose persisted result uses the structured failed `tool_result` contract
- **THEN** the tool output data includes `tool_status: "failed"`
- **AND** the tool output data includes a non-empty `tool_error` string derived from that structured failure result

#### Scenario: Streaming a failed plain-text tool output during migration
- **WHEN** the backend streams a user-visible tool output message whose result uses a legacy plain-text failure shape that is recognized as a tool error
- **THEN** the tool output data includes `tool_status: "failed"`
- **AND** the tool output data includes a non-empty `tool_error` string

#### Scenario: Tool output has no extractable error text
- **WHEN** the backend identifies a user-visible tool output as failed but cannot extract a specific error message
- **THEN** the tool output data includes `tool_status: "failed"`
- **AND** the tool output data includes a generic non-empty Tool Error Summary

#### Scenario: Stream enrichment receives a previously failed tool output
- **WHEN** live stream enrichment processes a tool output message that is already marked as failed by an earlier canonical failure signal
- **THEN** the backend preserves `tool_status: "failed"`
- **AND** the backend SHALL NOT overwrite that terminal status back to `success`

### Requirement: Chat history reads SHALL rebuild Tool Call Status presentation
The backend SHALL rebuild Tool Call Status fields for saved chat history responses from persisted tool-use and tool-result records without requiring `tool_status` or `tool_error` to be stored in agent memory. History rebuild SHALL prefer the canonical structured failed `tool_result` contract and SHALL keep legacy plain-text failure detection as a fallback.

#### Scenario: Reading history with a saved tool use
- **WHEN** the chat history API rebuilds messages from a saved user-visible tool-use record
- **THEN** the rebuilt tool call message data includes `tool_status: "running"`

#### Scenario: Reading history with a successful saved tool result
- **WHEN** the chat history API rebuilds messages from a saved user-visible tool-result record whose result is not identified as an error
- **THEN** the rebuilt tool output message data includes `tool_status: "success"`
- **AND** the rebuilt tool output message data includes `tool_error: null`

#### Scenario: Reading history with a structured failed saved tool result
- **WHEN** the chat history API rebuilds messages from a saved user-visible tool-result record whose result uses the structured failed `tool_result` contract
- **THEN** the rebuilt tool output message data includes `tool_status: "failed"`
- **AND** the rebuilt tool output message data includes a non-empty `tool_error` string

#### Scenario: Reading history with a legacy failed saved tool result
- **WHEN** the chat history API rebuilds messages from a saved user-visible tool-result record whose result uses a recognized legacy plain-text failure shape
- **THEN** the rebuilt tool output message data includes `tool_status: "failed"`
- **AND** the rebuilt tool output message data includes a non-empty `tool_error` string
