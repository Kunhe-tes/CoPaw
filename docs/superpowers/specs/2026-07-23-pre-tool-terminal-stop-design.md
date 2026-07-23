# PreToolUse Terminal Stop Design

## Goal

Allow every `PreToolUse` hook handler to explicitly terminate the current Main Agent turn after rejecting a pending tool call, without closing the chat session or making another model call.

## Public Contract

The canonical hook result is `{"decision":"stop","reason":"…"}`. Command and HTTP handlers continue to accept the existing `{"continue":false,"stopReason":"…"}` form. Prompt handlers gain `decision: "stop"` support while retaining their strict `{decision, reason}` output shape.

Only an explicit `stop` triggers terminal behavior. `deny`, `block`, handler failures, and `failPolicy: block` retain their existing recoverable behavior.

## Runtime Flow

`HookDecision.STOP` remains the strongest merged decision. For `PreToolUse`, the first stop in resolved handler order is authoritative: later decisions and `updatedInput` outputs cannot replace it. A stopped tool call emits the normal failed tool-result presentation with `error_type: "hook_stopped"` and retains it in agent memory.

The tool-call execution layer reports a terminal-stop signal to the turn runner. The runner treats that signal as a hard terminal outcome: it prevents any next agent-model turn, emits and persists the hook reason as the final assistant message, records the attempt as blocked, and skips `BeforeStop` and `Stop` hooks. When the reason is empty, the final message is `Hook requested stop`; `suppressOutput` never hides it.

For parallel tool calls, the terminal signal prevents unstarted calls and requests cancellation of cancellable in-flight calls. Completion does not promise rollback of external side effects.

`STOP` behavior for hook events other than `PreToolUse` remains unchanged.

## Components

- `src/swe/agents/hook_runtime/output.py` normalizes canonical stop output, including prompt-hook output.
- `src/swe/agents/hook_runtime/merge.py` preserves a pre-tool stop over later input-conflict processing.
- `src/swe/agents/tool_guard_mixin.py` distinguishes `hook_stopped`, records the rejected tool result, and exposes terminal-stop state to the agent turn.
- `src/swe/app/runner/runner.py` observes terminal-stop state, emits/persists the assistant final response, and ends the lifecycle without follow-up hooks or model calls.

## Error Handling and Compatibility

Existing `continue: false` command/HTTP output remains valid. Existing non-stop denial paths, automatic approval behavior, regular lifecycle hooks, and other event types must not change. Missing stop reasons use the stable fallback; raw handler failures do not become terminal stops.

## Test Strategy

Unit tests cover canonical stop normalization for generic and prompt handlers, stop precedence over conflicting updates, `hook_stopped` tool-result creation, and unchanged deny/block behavior. Runner tests cover the terminal response, memory persistence, no follow-up model invocation, lifecycle-hook skipping, fallback reason, `suppressOutput` immunity, and ordinary session reuse on the next user turn. Existing parallel-call tests are extended or added to assert that a stop requests cancellation and prevents queued peer calls.
