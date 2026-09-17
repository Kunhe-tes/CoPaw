# Stop Output Transformation Design

**Status:** Approved

## Goal

Allow an explicitly configured Stop Hook to replace the final assistant text
before completion. The feature supports tenant, Agent Profile, and explicitly
activated Skill Hooks while preserving `Stop` as the single completion gate.
It implements [ADR 0029](../../adr/0029-stop-output-transformations-use-strict-two-phase-finalization.md).

## Scope

The feature is text-only. It transforms an extractable `assistant_response`,
including string content and `text` blocks, and never alters media,
attachments, tool cards, or other structured output.
Tool progress, approval, and non-response events remain live. A turn without
extractable assistant text does not start a transformation pipeline.

`outputTransform: true` is valid only on a `Stop` handler and is incompatible
with `once: true`. It is opt-in, so existing Hook configuration and ordinary
Stop behavior remain unchanged.

## Handler contract

Command, HTTP, and prompt transformers share one output shape:

```json
{
  "decision": "allow",
  "reason": "formatted response",
  "hookSpecificOutput": {
    "replacementText": "the complete replacement text"
  }
}
```

A transformer may omit `replacementText` to pass its current text through.
When supplied, it must be a string containing non-whitespace content and is
preserved exactly. A transformer cannot return `block`; completion blocking
remains the responsibility of a non-transforming Stop handler. An undeclared
handler that returns `replacementText` has invalid output.

Prompt handlers keep their structured decision/reason response and gain only
the optional nested `hookSpecificOutput.replacementText` field when configured
as transformers.

## Two-phase completion flow

When at least one transformer can match the current completion attempt by
event and matcher scope, the runner withholds candidate assistant text before
evaluating any text-dependent `if` expression and executes this flow:

```text
candidate assistant text
  -> serial Stop Output Transformation Pipeline
     tenant handlers
     -> Agent Profile handlers
     -> activated Skill handlers by skill_name
  -> replace this turn's assistant memory with the final pipeline text
  -> concurrent Stop Validation Phase on final text
  -> allow: deliver and persist final text
  -> block: retain final text for bounded automatic follow-up
```

Within every source, matcher groups and handlers retain declaration order.
Each transformer evaluates its `if` expression just before it runs, against
the current pipeline text. A potential transformer that evaluates false passes
through the text, but does not restore live streaming for that attempt. After
transformation, the validation phase resolves its matching handlers and
conditions against the final text. Validators retain the existing `allow` /
`block` merge behavior.

Only explicitly activated Skills may contribute transformers. Existing source
precedence is fixed as tenant, Agent Profile, then activated Skills; multiple
Skills use lexical `skill_name` order rather than session activation order.

## State, snapshots, and retention

After transformation and before validation, the runtime replaces the final
assistant message in Agent memory. The final transformed text is consequently
the only version used by automatic follow-up turns, session persistence,
monitor indexing, and response-derived suggestions. It is also the sole text
delivered after validation allows completion.

Conversation snapshots keep their existing behavior. A handler that sets
`includeConversationSnapshot: true` may receive the original candidate in its
snapshot even though its `assistant_response` contains the current pipeline
text. Swe does not persist original-candidate plaintext for a transformed
attempt in its controlled session, monitor, suggestion, or Hook telemetry
paths. Configured external HTTP handlers and model providers retain the data
responsibilities of content already sent to them.

## Failure and timing rules

The Agent Profile Hook runtime configuration adds
`max_stop_transform_seconds`, defaulting to 30 seconds. Tenant and Skill
configuration cannot raise it. A transformer's effective timeout is the lower
of its configured timeout and the remaining pipeline budget.

- A transformer failure or invalid replacement with `failPolicy: allow`
  records diagnostics, retains the current text, and continues the pipeline.
- A transformer failure with `failPolicy: block`, or pipeline-budget
  exhaustion, ends the request incomplete. It does not deliver text, execute
  unstarted handlers, or schedule an automatic follow-up.
- A validator `block` follows the existing bounded Stop automatic-follow-up
  behavior, but the follow-up receives the final transformed text.

## Observability and manual test

Each transformation attempt emits a best-effort application log containing
handler IDs and sources, whether replacement occurred, input/final lengths,
SHA-256 summaries, duration, and failure or budget state. Neither candidate
nor replacement text is written to that log; logging failure does not affect
completion delivery.

The existing Agent Profile Hook manual test supports a single output
transformer with an editable sample assistant response and shows that handler's
result. It does not simulate a full cross-source pipeline, mutate a live
session, or deliver an answer.

## Verification

- Schema tests cover valid transformer configuration, invalid non-Stop and
  once-only configuration, and the shared command/HTTP/prompt output contract.
- Runtime tests cover serial text replacement, source and Skill ordering,
  dynamic `if` evaluation, validator concurrency on final text, and no change
  to ordinary Stop handlers.
- Runner tests prove candidate-text buffering, final-memory replacement,
  final-only monitor/suggestion indexing, follow-up context, text-only scope,
  transformation failures, and total-budget exhaustion.
- Manual-test, telemetry, documentation, and existing Stop regression tests
  preserve their documented behavior.

## Out of scope

- Transforming or suppressing media, attachments, tool cards, or arbitrary
  structured message blocks other than text blocks.
- A full-pipeline interactive console preview.
- Original-candidate audit storage beyond the declared best-effort metadata.
- Backward compatibility with an old runtime during deployment; this feature
  is released through an all-instance update.
