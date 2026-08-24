## 1. Test Coverage First

- [ ] 1.1 Add backend tests for `GET /agent/context-occupancy?session_id=...` response shape, denominator from `running.max_input_length`, and unavailable/error behavior.
- [ ] 1.2 Add backend tests proving draft input and cumulative token usage are excluded from `used_tokens`.
- [ ] 1.3 Add backend tests for effective-context counting with completed compressed summary and already-compacted raw history excluded.
- [ ] 1.4 Add backend tests for status thresholds: `normal`, `warning`, `danger`, and `overflow`.
- [ ] 1.5 Add backend tests for cache hit and invalidation when session state version or relevant running/compaction configuration changes.
- [ ] 1.6 Add frontend tests for the circular indicator available state, unavailable grey ring, tooltip copy, and no persistent percentage text.
- [ ] 1.7 Add frontend tests for quiet refresh behavior: previous value remains visible, no spinner/updating label, and generation refreshes only after completion.
- [ ] 1.8 Add frontend tests proving typing draft input does not trigger occupancy refresh.

## 2. Backend Occupancy API

- [ ] 2.1 Run GitNexus impact analysis before editing the Agent router or related symbols.
- [ ] 2.2 Add a response model for context occupancy with `used_tokens`, `max_input_length`, `ratio`, `status`, `estimated`, and optional diagnostic fields that are not required by the UI.
- [ ] 2.3 Add a read-only Agent route for `GET /agent/context-occupancy?session_id=...` using existing tenant/source/agent request resolution.
- [ ] 2.4 Return a clear unavailable response or appropriate error for missing/unknown session state without crashing the Console.
- [ ] 2.5 Ensure the route does not mutate session state, memory state, or compaction state while estimating.

## 3. Backend Effective Context Estimation

- [ ] 3.1 Implement an estimator that loads the requested session state and reconstructs the effective persisted Main Agent context.
- [ ] 3.2 Include system prompt, completed compressed summary, effective uncompressed history messages, and compacted tool-result content in the token count.
- [ ] 3.3 Exclude unsent composer draft text, cumulative billing/token-usage records, and already-compacted raw history.
- [ ] 3.4 Count tokens with `get_swe_token_counter(agent_config)` and relevant Agent token-counting configuration.
- [ ] 3.5 Compute `ratio` from raw `used_tokens / max_input_length` and classify status with the agreed visual thresholds.
- [ ] 3.6 Keep comments/docstrings in modified Python files in Simplified Chinese per repository policy.

## 4. Backend Cache

- [ ] 4.1 Implement a bounded in-process cache for occupancy estimates.
- [ ] 4.2 Build the cache key from tenant/source scope, agent id, session id, session state version signal, and relevant running/compaction config fingerprint.
- [ ] 4.3 Invalidate naturally on session state save/mtime change, `max_input_length` change, context compaction config change, tool-result compaction config change, or token-counting config change.
- [ ] 4.4 Ensure cache use is an optimization only and stale/missing cache entries fall back to fresh computation.

## 5. Frontend API And State

- [ ] 5.1 Add TypeScript API types and client method for the context occupancy endpoint.
- [ ] 5.2 Add Chat page state or hook to store occupancy by active logical session id while preserving the previous value during refresh.
- [ ] 5.3 Trigger refresh on page entry, active session switch, chat history reload, model switch, Agent running-config change, and stream completion.
- [ ] 5.4 Do not trigger refresh on composer draft typing.
- [ ] 5.5 During generation, keep the previous value and request a fresh value only after stream completion.

## 6. Frontend Indicator UI

- [ ] 6.1 Add a compact circular context occupancy indicator component with status colors and ring fill.
- [ ] 6.2 Render no persistent percentage text beside or inside the ring.
- [ ] 6.3 Add hover/focus tooltip showing approximate `used / max`, percentage, estimated wording, and status explanation.
- [ ] 6.4 Show a grey empty ring and unavailable tooltip when no value is available or estimation fails.
- [ ] 6.5 Place the indicator immediately to the left of the submit button in the standard bottom composer.
- [ ] 6.6 Place the indicator immediately to the left of the submit button in the new-chat welcome composer if that composer can submit.
- [ ] 6.7 Add the narrowest composer action-row extension needed to achieve placement without disturbing existing quick-menu, upload, speech, cancel, or submit behavior.

## 7. Verification

- [ ] 7.1 Run focused backend pytest files for the new occupancy API, estimator, and cache.
- [ ] 7.2 Run focused frontend tests for Chat, runtime input/composer, welcome composer, and occupancy indicator.
- [ ] 7.3 Run broader relevant test suites with `venv/bin/python -m pytest` and `pnpm test:run` scopes appropriate to touched files.
- [ ] 7.4 Manually verify in the browser that the ring appears left of submit, remains quiet during refresh/generation, and tooltip text is correct.
- [ ] 7.5 Run `gitnexus_detect_changes()` before any commit to verify changed symbols and affected flows match this plan.
