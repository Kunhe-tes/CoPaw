# PreToolUse stop ends the current Main Agent turn

A `PreToolUse` hook may explicitly return `{"decision":"stop","reason":"…"}` to reject the pending tool call and end only the current Main Agent turn. This is distinct from `deny` and `block`, which allow the model to choose a different action. The decision is available to every handler type, wins over other hook outcomes and input updates, emits and persists its reason as the final assistant message, and records the rejected call as `hook_stopped`.

**Consequences**

- The terminal path prevents new model calls, skips later `BeforeStop` and `Stop` hooks, blocks unstarted peer tool calls, and requests best-effort cancellation of started peers; external side effects are not rolled back.
- Only an explicit `stop` selects this path. Handler failures and `failPolicy: block` remain ordinary, recoverable blocks.
- The standard protocol is `decision: "stop"`; command and HTTP hooks retain `continue: false` as a compatible legacy form. A missing reason uses the stable fallback `Hook requested stop`, and `suppressOutput` cannot hide the terminal message.
