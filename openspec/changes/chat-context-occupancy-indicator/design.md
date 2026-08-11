## Context

The Console Chat composer currently has an action row with quick-menu and submit controls. The standard bottom composer is implemented through `AgentScopeRuntimeWebUI/core/Chat/Input` and `ChatInput`, while the new-chat welcome composer uses a custom welcome layout.

Swe already tracks cumulative token usage for billing/analytics, but that data is not the same as context-window occupancy. Runtime context limits and compaction are driven by the Agent running configuration, especially `running.max_input_length`, `context_compact`, and tool-result compaction settings. The effective next Main Agent model input also depends on memory state, completed compressed summary, system prompt, and compacted tool results, so frontend-visible messages are insufficient for an accurate estimate.

## Goals / Non-Goals

**Goals:**

- Provide a backend-computed persisted context occupancy estimate for a scoped agent session.
- Use `running.max_input_length` as the denominator.
- Estimate effective persisted context after completed compaction, excluding unsent composer draft text.
- Cache estimates and invalidate them deterministically when session state or relevant configuration changes.
- Render a quiet circular indicator left of the Console Chat submit button.
- Refresh only on stable chat events: page entry, session switch, history reload, model/running-config changes, and stream completion.
- Keep the indicator non-disruptive during loading and generation.

**Non-Goals:**

- No click-through detail panel.
- No continuous polling.
- No inclusion of unsent composer draft text.
- No submission blocking based on occupancy status.
- No change to compaction trigger behavior.
- No use of provider-reported model context-window metadata in the first version.
- No attempt to show historical billing/token usage in the composer.

## Decisions

### Decision: Add a dedicated Agent context occupancy endpoint

Add a read-only endpoint such as `GET /agent/context-occupancy?session_id=...`.

Rationale:

- The value is scoped by tenant/source/agent/session and belongs to Agent runtime state.
- Mixing this into `/agent/running-config` would only provide the denominator.
- Mixing this into chat history would force the frontend to reload messages just to refresh an auxiliary indicator.

Alternative considered: compute in the frontend from chat messages. Rejected because frontend messages do not include system prompt, compressed summary, fixed runtime context, or compaction state accurately enough.

### Decision: Estimate with runtime-equivalent context inputs

The backend should resolve the current workspace and Agent config with the same tenant/source/agent request path used by existing Agent routes. It should load the requested session state, reconstruct or inspect effective memory state, include system prompt and completed compressed summary, apply the same tool-result compaction view where needed, and count with `get_swe_token_counter(agent_config)`.

Rationale:

- This keeps the estimate aligned with the runtime budget and token-counting configuration.
- Counting only visible chat messages would under-report fixed context and over-report already-compacted raw history.

Alternative considered: use tracing `total_input_tokens` from the previous model call. Rejected because it measures completed calls, not the current persisted state that will feed the next turn.

### Decision: Use Agent `running.max_input_length` as capacity

The denominator is the active Agent running configuration `max_input_length`, not model metadata.

Rationale:

- Runtime compaction and fit checks are configured against `max_input_length`.
- Current provider model metadata does not expose a reliable context-window field.
- This matches the existing Agent configuration UI label for maximum context length.

Alternative considered: infer model context windows from provider/model ids. Rejected as brittle and likely wrong for custom providers.

### Decision: Cache by scoped session state and config fingerprint

Cache entries should be keyed by:

- tenant/source scope identity;
- agent id;
- session id;
- session state version signal, preferably session state file mtime or equivalent content version;
- fingerprint of relevant running configuration, including `max_input_length`, `context_compact`, `tool_result_compact`, and token-counting settings.

Rationale:

- The user explicitly wants caching.
- A deterministic key avoids TTL-only staleness.
- Session saves and config changes naturally produce different keys.

Alternative considered: fixed TTL cache. Rejected as the main strategy because it can keep stale context risk visible after a stream completes or config changes. A TTL may still be used as a secondary memory bound.

### Decision: Return display-ready status but keep raw values

The endpoint should return raw `used_tokens`, `max_input_length`, `ratio`, `estimated`, and a display status. Status thresholds are `normal < 70%`, `warning >= 70%`, `danger >= 90%`, and `overflow >= 100%`.

Rationale:

- Returning status centralizes threshold semantics for tests and future clients.
- Returning raw values keeps the frontend simple without hiding exact estimate data.
- The threshold is visual only and must not affect submission.

Alternative considered: frontend-only status calculation. Acceptable, but backend status makes API tests clearer and prevents multiple clients from drifting.

### Decision: Render through composer action-row extension points

For the standard bottom composer, inject the indicator via the existing sender action/prefix area or a narrow extension near the submit button. If existing `sender.prefix` only places controls on the left side of the action row, add a more precise `actions` render hook or adjacent action slot so the indicator can sit immediately left of submit without disturbing quick-menu placement.

For the welcome composer, add a narrow prop or equivalent action-row extension so the same indicator can be placed next to its submit button.

Rationale:

- The indicator is semantically tied to submit readiness.
- It should not become a global header badge or sidebar metric.
- A narrow extension avoids redesigning the composer.

Alternative considered: place the indicator in the chat header. Rejected because the user asked for placement beside the submit button and because the metric is submit-context related.

### Decision: Keep refreshes quiet

The frontend keeps the last rendered value during refresh, shows no spinner or updating label, and only shows a grey empty ring when no value has ever been loaded or when the current session has no usable value. During generation, the previous value remains visible and a single refresh happens after completion.

Rationale:

- The indicator is auxiliary and should not distract from sending.
- Session state is most reliable after stream completion.
- The user explicitly prefers no loading affordance.

Alternative considered: show a spinner during refresh. Rejected as visually noisy for a small composer control.

## Risks / Trade-offs

- [Risk] Token estimate may differ from provider-side accounting. → Mitigation: mark tooltip copy as approximate and use the configured runtime token counter.
- [Risk] Counting effective context may accidentally mutate memory if it reuses compaction helpers directly. → Mitigation: implement estimation as read-only inspection or clone state before applying display-time compaction views.
- [Risk] Cache key may miss a relevant config field. → Mitigation: fingerprint the full relevant running subtrees instead of only `max_input_length`.
- [Risk] Multi-instance deployments may have per-process in-memory caches. → Mitigation: cache is an optimization only; deterministic invalidation keys keep correctness within each process and stale cross-process values are bounded by session/config version keys.
- [Risk] The exact "immediately left of submit" slot may require a small composer API change. → Mitigation: prefer the narrowest action-row extension and add component tests to lock placement.
- [Risk] Estimation could be expensive for very large sessions. → Mitigation: cache results and avoid refresh on typing or polling.

## Migration Plan

1. Add backend response model and endpoint for context occupancy.
2. Implement read-only effective context estimation and status classification.
3. Add scoped cache with deterministic invalidation key and bounded memory behavior.
4. Add frontend API client/types.
5. Add circular indicator component with tooltip and unavailable state.
6. Wire indicator into standard and welcome Console Chat composers immediately left of submit.
7. Trigger refresh on page entry, session switch, history reload, model/running-config changes, and stream completion.
8. Add backend and frontend tests.
9. Rollback by hiding the frontend indicator and disabling the endpoint route; no persisted migration is required.

## Open Questions

None. The grilling session resolved denominator, numerator scope, refresh timing, cache requirement, loading behavior, and tooltip behavior.
