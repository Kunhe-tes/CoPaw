# Tool-hook stop ends the current Main Agent turn

> Superseded in part by [ADR 0020](0020-stop-is-the-unified-completion-hook.md): `BeforeStop` no longer exists; `Stop` is the unified completion gate.

Any `PreToolUse`, `PostToolUse`, or `PostToolUseFailure` hook may explicitly return `{"decision":"stop","reason":"…"}` to end only the current Main Agent turn. This is distinct from `deny` and `block`, which allow the model to choose a different action. The decision is available to every handler type and emits and persists its reason as the final assistant message.

**Consequences**

- The terminal path prevents new model calls, skips the `Stop` completion hook, blocks unstarted peer tool calls, and requests best-effort cancellation of started peers; external side effects are not rolled back.
- `PreToolUse` stop rejects the pending call, wins over other hook outcomes and input updates, and records the rejected call as `hook_stopped`. Post-tool stop retains the already completed tool outcome; on `PostToolUseFailure`, it suppresses propagation of the original tool exception while preserving that failure for presentation and audit.
- Only an explicit `stop` selects this path. Handler failures and `failPolicy: block` remain ordinary, recoverable blocks. The standard protocol is `decision: "stop"`; command and HTTP hooks retain `continue: false` as a compatible legacy form. A missing reason uses the stable fallback `Hook requested stop`, and `suppressOutput` cannot hide the terminal message.
