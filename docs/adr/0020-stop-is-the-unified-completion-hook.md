# Stop Is the Unified Completion Hook

`Stop` is the single lifecycle event that evaluates a candidate Assistant Response before request completion. It replaces both the former `BeforeStop` completion gate and the observation-only `Stop` event.

Each matching Stop handler executes once per candidate completion attempt and may record or notify through its own external side effects. The runtime merges handler decisions: `allow` approves completion, while any explicit `block` vetoes it and may start a bounded automatic follow-up Agent turn. The next candidate response runs the same Stop handlers again, preserving attempt-level audit history.

Stop accepts only `allow` and `block`. A Stop handler failure under `failPolicy: block` ends the request incomplete and never retries the Agent; `failPolicy: allow` makes the failure diagnostic only. Tool-hook terminal-stop paths continue to bypass Stop.

This is intentionally non-compatible. `BeforeStop` is removed and any residual configuration is invalid. Keeping it as an alias or retaining an observation-only Stop would preserve two competing definitions of completion and make handler behavior ambiguous.
