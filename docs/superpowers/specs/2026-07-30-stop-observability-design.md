# Stop Observation-Only Design

**Goal:** Make the lifecycle event `Stop` observation-only: its handlers may run external telemetry or audit work, but no handler output may change the Agent request, session memory, or completion state.

## Scope

- Preserve execution of every configured `Stop` handler, including its normal external command, HTTP, or prompt side effects, telemetry, and `once` bookkeeping.
- After handlers complete, discard the merged `Stop` result without warning.
- Do not add hook-produced memory, final block messages, completion-state changes, session-title changes, input rewrites, output suppression, or `failPolicy`-driven blocking for `Stop`.
- Keep the `Stop` handler's own configuration and execution errors observable through existing telemetry only; they must not alter the request flow.

## Non-goals

- Do not change `BeforeStop`: `block` remains the completion gate that can schedule a bounded internal follow-up turn.
- Do not change `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, or `PostToolUseFailure`, including their `decision: "stop"` semantics.
- Do not remove the `Stop` event or prevent handlers from executing.

## Design

Canonicalize the merged result for `HookEventName.STOP` in the Hook Runtime after all matched handlers have executed and their operational bookkeeping has completed. The caller receives a new empty `MergedHookResult`; therefore both the existing runner and any future caller treat `Stop` as non-decisional by construction.

This is deliberately centralized in the runtime rather than handled only by the runner. It guarantees that `additionalContext`, decision fields, and future result fields cannot accidentally regain control-flow effects through another `Stop` caller.

## Verification

- Unit-test that a `Stop` handler returning each supported decision/effect yields an empty merged result.
- Unit-test that a `Stop` handler failure with `failPolicy: "block"` is also neutralized.
- Runner-test that `Stop` output neither emits a final block message nor marks the request incomplete, while the handler still executes.
- Retain tests showing `BeforeStop + block` schedules a bounded model follow-up and tool-event `stop` remains terminal.
- Update `wiki/hook` to describe `Stop` as an observation-only terminal event.
