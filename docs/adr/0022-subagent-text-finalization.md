# SubAgents Use Text Finalization

Supersedes [ADR 0021](0021-subagent-research-and-structured-finalization.md).

Background SubAgents will make one tool-free, plain-text terminal model call after research. The call receives only the original `DelegationSpec` and a bounded research record, and its non-empty text becomes the `summary` of the runtime-owned `AgentResult`. It does not request native structured output or parse JSON.

`AgentResult` retains trusted task identity, lifecycle status, metrics, and errors, but its only model-authored content is `summary`. The retired structured content fields, `DelegationSpec.expected_output`, and `SubAgentDefinition.output_contract` are removed without compatibility handling because this feature has not been deployed. The definition schema version remains unchanged.

The bounded research record favors newer messages. When a single message exceeds remaining capacity, the runtime truncates it and marks the record entry as truncated. A normal research completion whose terminal text call fails, times out, or returns blank produces a partial result using its research reply as the summary fallback; when no such reply exists, it uses a fixed finalization-failure summary. A research-phase failure remains failed, and terminal calls are never retried. A turn-limit result remains partial even if its terminal text call succeeds.

Background tool projections keep run lifecycle status at the top level and expose terminal `result` as `summary`, plus `error_code` only when terminal text finalization fails.
