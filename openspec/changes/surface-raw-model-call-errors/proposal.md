## Why

Model-call failures that exhaust retries currently collapse into generic stream errors or temporary diagnostic dump hints, leaving Console Chat users without the provider/runtime failure text needed to understand timeout, rate-limit, connection, provider-status, or exhausted empty-output failures. `CONTEXT.md` now defines **Raw Model Call Error Detail** as the canonical user-visible contract, so the runtime needs an explicit change plan for surfacing, retaining, and replaying those details without turning them into model-readable memory.

## What Changes

- Add a stable `model_call_failed` user-visible failure detail for Console Chat main conversation runs when a model call fails before returning usable model content.
- Preserve up to 8KB of original runtime/provider diagnostic text, with scenario-specific summary text, beginning/end truncation, and best-effort sensitive-fragment redaction.
- Use the final failed attempt after query/model retry exhaustion, including exhausted **Empty Model Output** when no provider error text exists.
- Prefer the innermost recognizable model/provider failure when exceptions are wrapped.
- Mark the affected turn as failed while preserving any usable model output already streamed before the failure.
- Persist the failure detail for user-visible chat history and completed-run replay, while excluding it from Agent memory and future model-readable context.
- Keep the detail visible in the current stream even if separate history persistence fails, and replay active runs only from the live TaskTracker buffer.
- Keep non-model runtime failures, retry-in-progress notices, stack traces, diagnostic dump paths, and intentionally attached prompt/request-body content outside this user-visible raw model-call detail.
- Do not add a dedicated retry action in the first version; users retry through the existing chat input.

## Capabilities

### New Capabilities
- `model-call-error-detail`: Defines the user-visible failure detail contract for failed model calls in Console Chat, including extraction, redaction, truncation, streaming, persistence, and replay boundaries.

### Modified Capabilities
- `query-error-retry`: Clarifies that retry exhaustion for model-call failures feeds the final failed attempt into `model-call-error-detail` instead of exposing retry-in-progress notices or generic internal errors as the final user-facing detail.

## Impact

- Backend runner failure path around `AgentRunner._stream_query_after_preflight()`, `_stream_single_query_attempt()`, `_handle_query_error()`, retry classification, and empty model output failures.
- Console channel/SSE serialization and active-run replay through `ConsoleChannel.stream_one()` and `TaskTracker`.
- Chat history/completed-run persistence and history loading paths for Console Chat.
- Frontend response rendering in `useChatRequest`, `AgentScopeRuntimeResponseBuilder`, and failed response card presentation.
- Tests for model/provider exception extraction, redaction/truncation, retry exhaustion, partial-output preservation, non-model error exclusion, active reconnect replay, and historical replay.
