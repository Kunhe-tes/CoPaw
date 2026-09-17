## 1. Failure Detail Extraction

- [x] 1.1 Add a model-call failure detail module that classifies timeout, rate-limit, connection, provider-status, exhausted Empty Model Output, and unknown model-call failures.
- [x] 1.2 Implement exception-chain traversal that prefers the innermost recognizable model/provider failure over generic wrapper exceptions.
- [x] 1.3 Extract provider/runtime detail text from common exception shapes, including `status_code`, response body/text, message fields, and chained causes.
- [x] 1.4 Add scenario-specific summaries and stable `model_call_failed` error code mapping.
- [x] 1.5 Implement best-effort sensitive-fragment redaction for authorization headers, bearer tokens, cookies, API keys, and secret-like key/value pairs.
- [x] 1.6 Implement 8KB beginning/end truncation with an explicit truncation marker.

## 2. Runner Integration

- [x] 2.1 Integrate the extractor at the final failed-attempt boundary in `AgentRunner._stream_query_after_preflight()`.
- [x] 2.2 Convert qualifying Console Chat model-call failures into terminal failed response events instead of allowing them to escape to TaskTracker as generic internal stream errors.
- [x] 2.3 Preserve existing handling for hook, tool, session storage, message persistence, cancellation, and other non-model runtime failures.
- [x] 2.4 Ensure exhausted Empty Model Output failures produce internal diagnostic detail when provider error text is unavailable.
- [x] 2.5 Ensure retry-in-progress notices are not included in the final raw model-call detail.
- [x] 2.6 Preserve already streamed usable assistant output when the final failed response event is emitted.

## 3. User-Visible Retention And Replay

- [x] 3.1 Persist `model_call_failed` details in the Console Chat user-visible history/completed-run replay surface.
- [x] 3.2 Prevent `model_call_failed` details from being written to Agent memory or included in later model-readable context.
- [x] 3.3 Keep current SSE stream emission independent from history persistence success.
- [x] 3.4 Confirm active reconnect replay uses the existing TaskTracker live buffer and does not reconstruct completed history mid-run.
- [x] 3.5 Exclude diagnostic dump paths, stack traces, prompts, and intentionally attached request bodies from persisted user-visible details.

## 4. Frontend Presentation

- [x] 4.1 Verify `useChatRequest` and `AgentScopeRuntimeResponseBuilder` render terminal failed response frames with `error.code = "model_call_failed"`.
- [x] 4.2 Preserve prior assistant output when a terminal failed response frame has empty or partial output.
- [x] 4.3 Ensure the error remains directly visible and is not hidden inside completed process disclosure.
- [x] 4.4 Avoid adding a dedicated retry action in the first version; retain existing chat input retry workflow.

## 5. Tests And Validation

- [x] 5.1 Add unit tests for classification and innermost wrapped exception extraction.
- [x] 5.2 Add unit tests for redaction, truncation, excluded diagnostic fields, and empty-output diagnostics.
- [x] 5.3 Add runner tests for retry exhaustion using the final failed attempt and excluding retry notices.
- [x] 5.4 Add runner/channel tests proving non-model runtime failures keep existing handling.
- [x] 5.5 Add stream tests proving current SSE emits `model_call_failed` even when history persistence fails.
- [x] 5.6 Add history replay tests proving failed details are restored for users but not reused as Agent memory/model context.
- [x] 5.7 Add frontend tests for failed response rendering and partial-output preservation.
- [x] 5.8 Run targeted backend and frontend tests for the changed paths.
