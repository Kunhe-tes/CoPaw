# Instrumentation Matrix

This contract describes future business-boundary hooks. Ticket 01 implements only the shared core; later tickets add the hooks.

| Boundary | Owner and identity | Parent / required metadata | Stable slot and end owner | Missing-data behavior |
|---|---|---|---|---|
| Request admission | Question admission; new `obs_run_id` | Scope, Chat, root question occurrence, run start, capture snapshot | `(run, obs_run_id, accepted, 0)`; admission owner | No durable admission means no Run; missing capture means disabled |
| Continuous Agent execution | Query owner; new `obs_attempt_id` | Run, attempt index, predecessor Attempt | `(attempt, obs_attempt_id, started/ended, 0)`; query settlement | Keep Run unresolved if settlement is absent |
| Agent operation | Agent invocation boundary; new `obs_span_id` | Attempt, parent Span when known, operation and bounded asset identity | `(span, obs_span_id, started/ended, 0)`; invocation owner | End may stand alone with `start_observed=false` |
| Logical model call | Provider call owner; one Span per logical call | Attempt, Agent parent, provider/request model, known Usage | Span start/end; provider wrapper at actual call boundary | Unknown Usage remains null; no call for planning or approval short-circuit |
| Physical model retry | Provider retry owner; attempt metadata within logical call | Logical model Span and retry ordinal | Stable event slot per retry ordinal; provider retry owner | Missing attempts do not change logical-call identity |
| Tool execution | Tool dispatcher; one Span per actual execution | Attempt, Agent parent, registered tool name | Span start/end; dispatcher | Guard rejection is separate and does not claim tool execution |
| Approval | Approval service; request identity | Run, producing Attempt, request ID and decision enum | `(approval, request_id, requested/resolved, 0)`; approval resolver | Missing persisted handoff marks unresolved; never infer approval |
| Background SubAgent | Worker launcher/worker; business SubAgent key and Span ID | Root Run, launching Attempt/parent Span, explicit serialized context | Start owned by launcher; end owned by worker | Missing worker end remains pending/unknown and cannot reopen root Run |
| Asset use | Actual executor; registered asset ID/version | Run, Attempt, containing Span | `(asset, use_event_id, used, 0)`; use site | Unknown historical version stays unknown |
| Content evidence | Authorized business resolver; message occurrence/tool call reference | Run and business locator, never body or NAS path | `(content_ref, reference_id, resolved, 0)`; resolver | pending/not_saved/compacted/unavailable are distinct |

## Core Call Sequence

1. Admission snapshots `SWE_AGENTOBS_ENABLED` into an `ObservabilityContext`.
2. The caller binds the context with `bind_context`; Attempt creation copies the Run identity and capture decision.
3. A real boundary opens a `SpanHandle`, emits a start record, and may emit bounded metadata facts.
4. The owner ends the handle with a business status; elapsed time uses a monotonic clock and the end event repeats its start time and parent.
5. Approval and worker boundaries pass `to_carrier()` explicitly and restore via `from_carrier()`. ContextVar propagation is process-local only.
6. The independent emitter projects allowed metadata, enforces per-event and total queue budgets, and writes JSONL to stdout.

The model layer has no emitter or database dependency. Context depends only on identity models; the facade depends on context/models/emitter. The emitter depends only on configuration and event serialization. It does not import `swe.tracing`.

Operation, reason, and display labels must come from trusted code/config registration through `register_metadata_label`; request-derived free text is rejected. Incremental facts use a span-local sequence for each phase so repeated facts retain distinct ingestion slots.
