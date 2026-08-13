# SubAgent Text Finalization Design

## Goal

Replace Background SubAgent native structured-output finalization with a single plain-text terminal summary while retaining the runtime-owned run envelope and execution isolation.

## Contract

- `AgentResult` retains trusted `task_id`, `agent_run_id`, `agent_name`, `status`, `metrics`, and `errors`.
- `summary` is its only model-authored content.
- Retire `expected_output` and `output_contract` from models, definitions, registration, built-ins, prompts, and tests without legacy compatibility.
- Leave the definition schema version unchanged.

## Runtime

After normal research completion or a research turn limit, the runtime passes the original `DelegationSpec` and a bounded research record to one ordinary, tool-free model call. It does not pass `structured_model`. The runtime reads non-empty final text and stores it as `AgentResult.summary`.

The record contains assistant replies, tool calls, and tool results but excludes the Main Agent conversation. It prioritizes newest messages; an oversized message is truncated to remaining capacity and marked `truncated`.

## Failure semantics

- Normal research plus non-empty terminal text is `completed`.
- Turn-limit research plus non-empty terminal text is `partial` with `research_turn_limit_reached`.
- A terminal timeout, exception, or blank text is not retried. Normal research falls back to its text reply (or the fixed research fallback) and returns `partial` with `text_finalization_failed`.
- Research-phase timeout or exception is `failed` and skips text finalization.

## Parent projection

The parent-facing record retains top-level lifecycle status. Its nested terminal result is `{ "summary": "..." }`; `error_code: "text_finalization_failed"` appears only when text finalization fails. It does not repeat result status or expose structured content, metrics, raw errors, policies, or worker diagnostics.
