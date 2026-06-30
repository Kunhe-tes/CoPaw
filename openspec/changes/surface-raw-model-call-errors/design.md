## Context

`CONTEXT.md` now defines **Raw Model Call Error Detail** as a user-visible failure detail for model-call failures that return no usable assistant content after retry exhaustion. Today the main Console Chat path runs through:

```
Console Chat
  -> ConsoleChannel.stream_one()
  -> AgentRunner.stream_query()
  -> _stream_query_after_preflight()
  -> _stream_single_query_attempt()
  -> _stream_completion_lifecycle()
  -> provider/model call
```

When the runner finally raises, `_handle_query_error()` writes a temporary diagnostic dump, appends a dump path to the exception, and re-raises. The TaskTracker producer catches the exception and emits a generic `{"error": "internal server error"}` SSE frame. That protects internals, but it also drops useful provider/runtime failure text and is not a stable response contract for the frontend or history replay.

The frontend already understands terminal failed response frames and preserves prior assistant output when a terminal failed response frame has empty output. The missing piece is a backend contract that emits and persists a failed response carrying the model-call detail instead of allowing model-call failures to escape as generic stream errors.

## Goals / Non-Goals

**Goals:**
- Surface model-call failures in Console Chat main conversation streams as terminal failed response events with stable code `model_call_failed`.
- Preserve the final failed attempt after retry exhaustion, including timeout, rate-limit, connection, provider status, and exhausted **Empty Model Output** failures.
- Extract the innermost recognizable model/provider failure from wrapped exceptions.
- Include a scenario-specific summary followed by bounded original error detail.
- Apply best-effort redaction and 8KB beginning/end truncation before the detail becomes user-visible or persisted.
- Persist the detail for user-visible completed-run/chat-history replay without adding it to Agent memory or future model-readable context.
- Preserve already streamed usable model output when the final model call fails.
- Keep active reconnect replay based on TaskTracker's existing live buffer.

**Non-Goals:**
- Adding a dedicated retry button or changing the existing user retry workflow.
- Changing retry policy, retry counts, or backoff behavior except for the final exhausted model-call failure presentation.
- Applying this contract to skill optimization, suggestion generation, provider connection tests, scheduled-run-only output, or non-model runtime failures.
- Exposing stack traces, diagnostic dump file paths, prompt text, request bodies, or retry-in-progress notices as raw model-call detail.

## Decisions

### 1. Emit a terminal failed response instead of throwing through TaskTracker

Model-call failures that qualify for this feature should be converted inside the runner into a terminal response event:

```
{
  "object": "response",
  "status": "failed",
  "error": {
    "code": "model_call_failed",
    "message": "<summary>\n\n<bounded detail>",
    "details": {
      "kind": "timeout|rate_limit|connection|provider_status|empty_model_output|unknown_model_call",
      "provider_status": 429,
      "truncated": true
    }
  }
}
```

The exact schema should follow the runtime response model accepted by AgentScope Runtime and the existing response builder, but the semantic contract is stable: `error.code` is `model_call_failed`, and `error.message` is the user-visible text.

Alternative considered: keep throwing and teach TaskTracker to inspect exceptions. That would couple the transport-level broadcaster to model semantics and would not preserve partially streamed response state as cleanly.

### 2. Add a dedicated classifier/extractor separate from query retry classification

`is_query_retryable()` answers "should this be retried?" A new model-call failure extractor should answer "is this final failure a model-call failure, and what detail is safe to show?" It should walk `__cause__` / `__context__`, prefer the innermost recognizable provider/model exception, and classify timeout, rate-limit, connection, provider status, and exhausted **Empty Model Output**.

Alternative considered: extend `is_query_retryable()` to return rich data. That mixes retry decisions with presentation and persistence concerns, and makes non-retryable provider failures awkward.

### 3. Treat exhausted Empty Model Output as a model-call failure with internal diagnostic text

When the model returns no usable content after the fixed single empty-output retry, the detail should use internal diagnostic text because there may be no provider error body. Reasoning content, tool-use content, structured content, and non-empty text remain usable content and must not trigger this failure.

Alternative considered: show a generic "empty response" message. That loses the diagnostic distinction introduced in `CONTEXT.md` and makes empty-output regressions difficult to identify.

### 4. Persist as user-visible history, not model memory

The failed response/detail should be retained in the same user-visible chat history/completed-run replay surface that restores ordinary assistant responses. It must not be added to Agent memory, next-turn prompt construction, or any model-readable context. This likely means storing it through the frontend-visible response/history path rather than `agent.memory.add()`.

If history persistence fails, the current SSE stream still emits the failed response. Active reconnect during the same run uses TaskTracker's live buffer only; completed-run replay uses persisted history only.

Alternative considered: write the detail to Agent memory for convenience. That violates the domain rule and risks feeding provider diagnostics back into later model calls.

### 5. Redact and truncate before emission and persistence

The extractor should build a bounded user-visible string before it is attached to a response event. Redaction should remove obvious sensitive fragments such as authorization headers, API keys, bearer tokens, cookies, and known secret-looking key/value pairs. Truncation should keep the beginning and end up to 8KB total, with an explicit truncation marker.

Alternative considered: emit raw text and let the frontend truncate. That would still leak full sensitive text over the wire and into browser/runtime buffers.

## Risks / Trade-offs

- Provider SDK exception shapes vary -> Mitigate with chain traversal, duck-typed `status_code`/`response`/`body`/`message` extraction, and unit tests with wrapped fake exceptions.
- Redaction is best-effort, not a hard security boundary -> Mitigate by excluding prompt/request bodies and diagnostic dumps, redacting common secret formats before persistence, and keeping logs separate from user-visible detail.
- Failed response schema could drift from AgentScope Runtime types -> Mitigate by adding backend serialization tests and frontend builder tests using actual SSE-shaped events.
- Persistence may accidentally feed history back into model input -> Mitigate with explicit tests for next-turn context construction and Agent memory state.
- Non-model runtime failures could be misclassified -> Mitigate by requiring recognizable model/provider/empty-output markers and preserving existing handling for hook, tool, storage, and persistence errors.
- Long partial outputs plus failed terminal events can confuse rendering -> Mitigate with frontend tests confirming prior output remains visible and the error remains directly visible.

## Migration Plan

1. Add the model-call failure extractor, redaction, and truncation helpers with unit coverage.
2. Integrate the extractor at the final failed-attempt boundary in `AgentRunner`, after retries are exhausted and before exceptions escape to TaskTracker.
3. Emit terminal failed response events for qualifying model-call failures; keep non-model failures on the existing error path.
4. Persist failed response details for user-visible history/completed-run replay without writing them to Agent memory.
5. Update frontend tests and rendering only if the existing failed response card does not clearly present `model_call_failed` details.
6. Add integration tests for stream, active reconnect replay, completed history replay, and persistence-failure fallback.

Rollback is straightforward: disable the extractor integration so qualifying failures return to the existing exception path. The helper code can remain unused without changing stored history format for successful runs.

## Open Questions

- Which exact AgentScope Runtime response/error model fields are safest for carrying optional structured `details` without breaking older frontend assumptions?
- Where is the narrowest persistence boundary for Console Chat completed-run history that is user-visible but guaranteed not to become next-turn model context?
- Should provider-specific diagnostics preserve HTTP response body snippets separately from the combined `message`, or is one bounded message sufficient for the first version?
