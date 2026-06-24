## Context

Swe currently mixes several failure representations for tool execution. Local built-in tools often encode failure as plain text, AgentScope catches arbitrary tool exceptions and converts them into text output, MCP tools may already expose `isError`, and runtime-owned paths such as hook denial or local hard timeout persist their own ad-hoc text results. That fragmentation leaks into two visible regressions: persisted `tool_result` records do not have a stable failure contract, and runner presentation layers can misclassify real failures as `success`, especially when a live stream path re-infers status from already-stringified output.

This change is cross-cutting because it affects tool execution entrypoints, built-in tools, runner status enrichment, and runtime-generated failure messages. It also needs a migration path because old plain-text failure results already exist in memory and history.

## Goals / Non-Goals

**Goals:**
- Define one canonical failed `tool_result` contract for local tools, MCP failures, and runtime-generated tool failures.
- Let Swe-controlled tools signal explicit failure through a dedicated `ToolExecutionError` contract instead of encoding failure as successful text output.
- Normalize unexpected tool exceptions into the same structured failed result shape at a Swe-controlled entrypoint rather than changing AgentScope globally.
- Keep raw failure detail in persisted `tool_result.output` for model reasoning while preserving bounded `tool_error` summaries for presentation.
- Preserve backward compatibility for historical and in-flight legacy plain-text failure results.

**Non-Goals:**
- Introduce a new model-visible but user-hidden storage channel for raw tool failure details.
- Rewrite every tool in the repository in one pass; the change only needs to migrate the high-value built-in and runtime-owned paths first.
- Replace MCP-native error semantics with a Swe-only protocol.
- Change run-level cancellation semantics or treat user interruption as a failed tool invocation when no tool failure result exists.

## Decisions

### Decision 1: Canonical failed tool output uses an MCP-style structured result

Persist failed tool invocations using a single shape:

```json
{
  "isError": true,
  "content": [
    { "type": "text", "text": "raw failure detail" }
  ],
  "error_type": "..."
}
```

This reuses semantics already recognized by MCP tools and existing runner logic, so the failure contract converges instead of adding a third incompatible result family.

Alternative considered: invent a Swe-only failure payload with top-level `error` or `ok=false`. Rejected because it would require more runner/front-end branching and would not align with MCP-native errors already present in the system.

### Decision 2: Add an explicit ToolExecutionError contract for tool-declared failure

Introduce `ToolExecutionError` for Swe-controlled tools to declare failure with an `error_type`, raw detail, and optional structured content overrides. Built-in tools that currently return error-looking text as a successful `ToolResponse` will migrate toward raising this exception.

Alternative considered: keep using plain `Exception` everywhere and infer type from strings. Rejected because it preserves ambiguous semantics and makes stable failure typing impossible.

### Decision 3: Normalize exceptions in a Swe-controlled tool execution wrapper

Catch `ToolExecutionError`, recognized subsystem exceptions, and generic exceptions in a Swe-owned toolkit wrapper or equivalent tool execution entrypoint created by `react_agent`, rather than modifying AgentScope's global `Toolkit.call_tool_function`.

This keeps the contract local to Swe, limits upgrade risk, and still covers built-in tools, skill tools, and exception paths under Swe's own agents.

Alternative considered: monkey-patch or fork AgentScope's `Toolkit.call_tool_function`. Rejected because it broadens blast radius and makes upstream version drift harder to manage.

### Decision 4: Runtime-generated tool failures use the same failure builder without throwing

Paths such as hook denial, auto-deny, approval denial, and local hard timeout already decide failure outside the normal tool-body exception flow. These paths should call the same shared structured-failure builder directly instead of raising synthetic exceptions through unrelated control flow.

Alternative considered: force runtime-owned failure paths to raise `ToolExecutionError` and re-enter the tool execution wrapper. Rejected because those paths already own message persistence and are not naturally modeled as tool-body exceptions.

### Decision 5: Tool status remains a presentation derivation with backward-compatible fallback

`tool_status` and `tool_error` remain derived presentation fields. Runner logic should prefer canonical structured failure results, preserve any pre-existing failed status, and retain legacy plain-text heuristics only as a migration fallback for stored or not-yet-migrated outputs.

Alternative considered: remove plain-text fallback immediately after adding the new contract. Rejected because existing history and partially migrated runtime paths would still misclassify failures.

## Risks / Trade-offs

- [Partial migration leaves mixed failure shapes in the short term] → Keep legacy plain-text failure detection in runner status logic until migrated paths are complete.
- [Raw failure detail stays user-visible when raw tool output is exposed in the UI] → Preserve bounded `tool_error` as the main presentation summary and document that raw tool output remains visible if expanded.
- [Wrapping tool execution in Swe could diverge from AgentScope behavior] → Keep the wrapper narrow, focused on exception normalization and result conversion, and avoid changing unrelated streaming semantics.
- [Broad exception normalization can hide programming mistakes] → Preserve structured `error_type` distinctions, keep raw details in the failure result, and continue logging/trace reporting for debugging.

## Migration Plan

1. Add the shared `ToolExecutionError` and structured-failure builder.
2. Introduce the Swe-owned tool execution wrapper and use it from agent toolkit creation.
3. Migrate high-value built-in tools and runtime-owned failure writers to the new contract.
4. Update runner tool-status enrichment to prefer structured failures, preserve existing `failed` status, and retain legacy fallback heuristics.
5. Cover the migrated paths with unit tests for both canonical and legacy failure shapes.

## Open Questions

- None for the initial implementation; the remaining trade-off is accepted visibility of raw failure detail in persisted tool output.
