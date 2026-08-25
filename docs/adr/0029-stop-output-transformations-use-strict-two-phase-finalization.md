# Stop Output Transformations Use Strict Two-Phase Finalization

**Status:** Accepted. This ADR refines [ADR 0020](0020-stop-is-the-unified-completion-hook.md): `Stop` remains the sole completion gate, but an explicitly declared output transformer may replace the candidate Assistant Response text before that gate completes. We choose a two-phase design so that a handler can rewrite text deterministically without weakening the concurrent validation and audit model of ordinary Stop handlers.

## Decision

`outputTransform: true` is valid only for a non-once `Stop` handler. Command, HTTP, and prompt handlers use the same `hookSpecificOutput.replacementText` contract; a transformer may allow and either replace or pass through the current non-empty text, but may not block. Transformers execute serially for every eligible candidate in fixed source order: tenant, Agent Profile, then explicitly activated Skills ordered by `skill_name`; their conditions see the current pipeline text. Ordinary Stop handlers are resolved only after this pipeline and continue to execute concurrently against its final text, retaining the existing `allow` / `block` completion decision.

The presence of a potentially matching transformer invokes strict finalization before its text-dependent condition is evaluated: candidate assistant text is withheld while transformation and validation run, then only the approved final text is delivered and placed in Agent memory. This applies to text only; tool progress and other non-response events remain live, and media, attachments, tool cards, and other structured output are outside this feature. A blocked follow-up receives the final transformed text, not the original candidate. Existing conversation-snapshot behavior is deliberately unchanged, so an explicitly requested snapshot can still contain the original candidate.

The Agent Profile owns a thirty-second default total transformation budget, which tenant and Skill configuration cannot raise. A transformer failure with `failPolicy: allow` passes through the current text and continues; a blocking failure or budget exhaustion ends the request incomplete without delivery or automatic follow-up. Swe persists no original-candidate plaintext for transformed attempts: final response paths use the replacement, while best-effort application logs retain only handler/source identity, lengths, SHA-256 summaries, timing, and failure state.

## Consequences

Existing Stop configurations remain unchanged because transformation is opt-in. The Hook Runtime, runner delivery boundary, Agent memory replacement, prompt output validation, telemetry, controlled Hook manual test, and automated test suite must jointly enforce this contract; a transformation cannot be implemented solely by accepting an additional handler-output field.
