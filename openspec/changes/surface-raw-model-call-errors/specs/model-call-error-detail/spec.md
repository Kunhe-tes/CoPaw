## ADDED Requirements

### Requirement: Raw model-call failures are surfaced to Console Chat
The system SHALL surface qualifying Console Chat main conversation model-call failures as user-visible failed turns with stable error code `model_call_failed`.

#### Scenario: Timeout failure is surfaced
- **WHEN** a Console Chat main conversation model call ultimately fails with a timeout before returning usable model content
- **THEN** the streamed turn is marked failed
- **AND** the user-visible error code is `model_call_failed`
- **AND** the user-visible message includes a timeout-specific summary followed by bounded original error detail

#### Scenario: Rate-limit failure is surfaced
- **WHEN** a Console Chat main conversation model call ultimately fails with a rate-limit error before returning usable model content
- **THEN** the streamed turn is marked failed
- **AND** the user-visible error code is `model_call_failed`
- **AND** the user-visible message includes a rate-limit-specific summary followed by bounded original error detail

#### Scenario: Connection failure is surfaced
- **WHEN** a Console Chat main conversation model call ultimately fails with a connection error before returning usable model content
- **THEN** the streamed turn is marked failed
- **AND** the user-visible error code is `model_call_failed`
- **AND** the user-visible message includes a connection-specific summary followed by bounded original error detail

#### Scenario: Provider status failure is surfaced
- **WHEN** a Console Chat main conversation model call ultimately fails with a provider status error before returning usable model content
- **THEN** the streamed turn is marked failed
- **AND** the user-visible error code is `model_call_failed`
- **AND** the user-visible message includes a provider-status-specific summary followed by bounded original provider diagnostic detail

#### Scenario: Exhausted empty output failure is surfaced
- **WHEN** a Console Chat main conversation model call returns **Empty Model Output** after the fixed empty-output retry is exhausted
- **THEN** the streamed turn is marked failed
- **AND** the user-visible error code is `model_call_failed`
- **AND** the user-visible message includes an empty-output-specific summary followed by bounded internal diagnostic detail

### Requirement: Model-call detail uses the final recognizable failure
The system SHALL build **Raw Model Call Error Detail** from the final failed model-call attempt and prefer the innermost recognizable model or provider failure when exceptions are wrapped.

#### Scenario: Retry exhaustion uses final attempt
- **WHEN** a model-call failure is retried and every retry fails
- **THEN** the user-visible detail is built from the final failed attempt
- **AND** retry-in-progress notices are not included in the raw model-call detail

#### Scenario: Wrapped provider exception is inspected
- **WHEN** a model/provider failure is wrapped by one or more outer exceptions
- **THEN** the user-visible detail uses the innermost recognizable model/provider failure
- **AND** unrelated outer wrapper text is not preferred over provider diagnostics

#### Scenario: Non-model wrapper remains excluded
- **WHEN** an exception chain contains only hook, tool, storage, message persistence, or other non-model runtime failures
- **THEN** the failure is not labeled with `model_call_failed`
- **AND** existing non-model failure handling is used

### Requirement: User-visible detail is bounded and redacted
The system SHALL apply best-effort sensitive-fragment redaction and 8KB maximum truncation before **Raw Model Call Error Detail** is streamed or persisted.

#### Scenario: Sensitive fragments are redacted
- **WHEN** provider or runtime error text contains recognizable authorization headers, bearer tokens, cookies, API keys, or secret-like key/value fragments
- **THEN** those fragments are redacted before the detail is emitted to the frontend
- **AND** the unredacted fragments are not persisted in user-visible chat history

#### Scenario: Long detail is truncated
- **WHEN** the redacted original error detail exceeds 8KB
- **THEN** the user-visible detail keeps the beginning and end of the text
- **AND** the user-visible detail marks that truncation occurred
- **AND** the emitted and persisted detail does not exceed the configured user-visible limit

#### Scenario: Excluded diagnostic content is omitted
- **WHEN** model-call failure handling has access to stack traces, diagnostic dump paths, prompts, or intentionally attached request bodies
- **THEN** those fields are excluded from **Raw Model Call Error Detail**

### Requirement: Failed model-call turns preserve streamed usable output
The system SHALL preserve any usable model output already streamed before a qualifying model-call failure is emitted.

#### Scenario: Partial assistant output remains visible
- **WHEN** a model call streams usable assistant output and later fails before the turn completes
- **THEN** the terminal failed turn preserves the already streamed usable output
- **AND** the error remains directly visible on the failed turn

#### Scenario: No usable output still shows error
- **WHEN** a qualifying model-call failure occurs before any usable assistant output is streamed
- **THEN** the failed turn still renders the user-visible `model_call_failed` detail directly

### Requirement: Model-call detail has separate user-visible retention
The system SHALL retain **Raw Model Call Error Detail** for user-visible chat history and completed-run replay without storing it in Agent memory or reusing it as later model-readable context.

#### Scenario: Completed history replays failed detail
- **WHEN** a user reloads a completed Console Chat conversation containing a failed model-call turn
- **THEN** the failed turn is restored with its `model_call_failed` detail
- **AND** the detail remains user-visible

#### Scenario: Active reconnect uses live buffer
- **WHEN** a user reconnects to an active Console Chat run after a model-call failure detail has already been emitted but before the run is cleaned up
- **THEN** the reconnect stream replays the detail from the active run's live buffer

#### Scenario: Detail is not model-readable memory
- **WHEN** the user sends a later turn in the same session
- **THEN** the previous **Raw Model Call Error Detail** is not added to Agent memory
- **AND** the previous detail is not included as model-readable context for the later model call

#### Scenario: Persistence failure does not hide current stream detail
- **WHEN** user-visible history persistence fails after a qualifying model-call failure
- **THEN** the current stream still emits the `model_call_failed` detail
- **AND** the persistence failure does not replace the current stream detail with a generic internal error

### Requirement: First version scope is limited to Console Chat main stream
The system SHALL apply **Raw Model Call Error Detail** only to Console Chat's main conversation stream in the first version.

#### Scenario: Skill optimization remains out of scope
- **WHEN** a frontend-triggered skill optimization model call fails
- **THEN** it is not required to emit `model_call_failed` under this capability

#### Scenario: Suggestions remain out of scope
- **WHEN** backend suggestion generation fails
- **THEN** it is not required to emit `model_call_failed` under this capability

#### Scenario: Provider connection tests remain out of scope
- **WHEN** a provider connection test model call fails
- **THEN** it is not required to emit `model_call_failed` under this capability

#### Scenario: Dedicated retry action is not shown
- **WHEN** a failed Console Chat turn shows **Raw Model Call Error Detail**
- **THEN** the UI does not add a dedicated retry action for the first version
- **AND** users can retry through the existing chat input workflow
