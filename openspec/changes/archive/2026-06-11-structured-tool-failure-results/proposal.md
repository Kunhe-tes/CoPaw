## Why

The runtime currently reports many real tool failures as plain-text output, which causes `tool_result` semantics to drift across local tools, MCP tools, hook denials, and runtime-generated timeouts. That inconsistency makes Tool Call Status unreliable in live streams and rebuilt history, and it forces the frontend to infer failure from ad-hoc strings instead of a stable contract.

## What Changes

- Introduce a canonical structured failed `tool_result` contract for tool and runtime failure paths, using an MCP-style `isError=true` payload with typed failure metadata.
- Add an explicit `ToolExecutionError` contract so built-in tools and other local tool paths can signal failure without encoding errors as successful plain-text output.
- Route runtime-generated failures such as hook denial, auto-deny, and local hard timeout through the same structured failure builder instead of emitting bespoke text-only results.
- Update Tool Call Status presentation so live stream enrichment and chat-history rebuild prefer structured failure results, preserve previously failed status, and keep bounded `tool_error` summaries for the user-facing layer.
- Preserve backward compatibility by keeping plain-text failure detection as a fallback during migration.

## Capabilities

### New Capabilities
- `structured-tool-failure-results`: Canonical failed `tool_result` payloads for tool-declared and runtime-generated failures.

### Modified Capabilities
- `tool-call-status-presentation`: Terminal tool status detection now prefers the canonical structured failure contract and must not regress failed results back to success during stream enrichment or history rebuild.

## Impact

- Affected code spans built-in tools, Swe-controlled tool execution entrypoints, runner tool-status enrichment, and runtime-generated tool failure paths in `tool_guard_mixin`.
- MCP failures, hook denials, shell failures, and local tool timeouts converge on one persisted failure shape.
- Existing frontend `tool_error` behavior remains bounded and user-facing, while raw failure detail remains available in `tool_result.output` for model reasoning and debugging.
