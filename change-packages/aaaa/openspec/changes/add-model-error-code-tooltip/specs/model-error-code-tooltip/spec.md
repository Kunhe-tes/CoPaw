## ADDED Requirements

### Requirement: Error Summary Exposes Model Error Code Breakdown

The Monitor error summary endpoint SHALL include a top-10 breakdown of model error codes for model error rows only.

#### Scenario: Model error codes are aggregated

- **GIVEN** `swe_tracing_spans` contains `llm_input` rows with non-empty `error` text containing `Error code: 404 - ...` and `Error code: 504 - ...`
- **WHEN** the Console requests `/monitor/tracing/error/summary`
- **THEN** the response includes `model_error_codes` entries with the parsed codes and counts
- **AND** the existing `total_errors`, `model_errors`, and `tool_errors` counts remain unchanged.

#### Scenario: Existing filters are applied

- **GIVEN** the request includes source, date range, or BBK filters
- **WHEN** model error codes are aggregated
- **THEN** the code breakdown uses the same filtering scope as the existing error summary counts.

#### Scenario: Tool errors are excluded

- **GIVEN** `tool_call_end` rows contain error text with `Error code: 404 - ...`
- **WHEN** model error codes are aggregated
- **THEN** those tool error rows do not contribute to `model_error_codes`.

#### Scenario: Unrecognized model errors are skipped

- **GIVEN** a `llm_input` error row has non-empty error text without a recognizable `Error code:` token
- **WHEN** model error codes are aggregated
- **THEN** that row still contributes to `model_errors`
- **AND** that row does not contribute to `model_error_codes`.

#### Scenario: String error codes are supported

- **GIVEN** a `llm_input` error row contains `Error code: AUTH_KEY_REVOKED - ...`
- **WHEN** model error codes are aggregated
- **THEN** `AUTH_KEY_REVOKED` is returned as the code value.

#### Scenario: Breakdown is limited

- **GIVEN** more than 10 distinct model error codes match the request filters
- **WHEN** model error codes are aggregated
- **THEN** only the top 10 codes by count are returned.

### Requirement: BusinessOverview Shows Model Error Code Tooltip

The BusinessOverview error-analysis legend SHALL show the top model error code counts when the operator hovers over the "模型报错" legend text.

#### Scenario: Model error legend hover shows code counts

- **GIVEN** the error summary response contains `model_error_codes` with `404: 3` and `504: 5`
- **WHEN** the operator hovers over the "模型报错" legend text
- **THEN** the tooltip shows rows equivalent to `404: 3个` and `504: 5个`.

#### Scenario: Tool error legend has no new tooltip

- **GIVEN** the error-analysis legend renders both "模型报错" and "工具报错"
- **WHEN** the operator hovers over "工具报错"
- **THEN** no model error code tooltip is shown.

#### Scenario: No parsed codes are available

- **GIVEN** `model_errors` is greater than zero and `model_error_codes` is empty
- **WHEN** the operator hovers over "模型报错"
- **THEN** the tooltip indicates that no recognizable model error codes were parsed.

#### Scenario: Detail modal remains unchanged

- **GIVEN** the operator opens "查看详情"
- **WHEN** error rows are displayed in the detail modal
- **THEN** the modal continues to show the original error text and does not replace it with the code breakdown.
