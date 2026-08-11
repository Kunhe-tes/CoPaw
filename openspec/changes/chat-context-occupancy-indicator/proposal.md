## Why

Users currently cannot see how much of the Main Agent context window is already occupied before continuing a Console Chat session. This makes long-running sessions opaque until compaction or context-limit behavior surprises the user.

## What Changes

- Add a backend context occupancy API that estimates persisted session context against the active Agent `running.max_input_length`.
- Estimate the context that would actually enter the next Main Agent model input after completed compaction, including system prompt, compressed summary, effective history messages, and compacted tool results.
- Exclude unsent composer draft text and cumulative billing/token usage from the indicator.
- Cache backend estimates and invalidate them when session state or relevant running/compaction configuration changes.
- Add a compact circular occupancy indicator immediately to the left of the Console Chat submit button.
- Show no persistent percentage text in the composer; expose approximate token counts, percentage, and status only in hover tooltip.
- Keep the indicator quiet during refresh and generation: preserve the previous value without spinner or updating text, and refresh once generation completes.
- Show a grey empty ring with unavailable tooltip when no value is available or estimation fails.

## Capabilities

### New Capabilities

- `chat-context-occupancy`: Estimates and displays persisted Main Agent context-window occupancy for Console Chat sessions.

### Modified Capabilities

None.

## Impact

- Backend Agent routing gains a read-only context occupancy endpoint, expected as `GET /agent/context-occupancy?session_id=...`.
- Backend estimation reuses tenant/source/agent request resolution, Agent running configuration, memory/session state, and the configured token counter.
- Backend cache storage must be scoped by tenant/source, agent, session, session-state version, and relevant running/compaction config fingerprint.
- Console Chat frontend adds API typing/client code and renders the indicator through the standard composer action area.
- Console Chat refresh wiring updates occupancy on page entry, session switch, history reload, model/running-config changes, and stream completion.
- Tests cover backend response semantics/cache invalidation and frontend quiet display/tooltip behavior.
