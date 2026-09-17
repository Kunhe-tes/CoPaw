## Proposal

Add a hover tooltip to the BusinessOverview error-analysis donut legend so operators can see the top model error codes behind "模型报错" without opening the detail modal.

The tooltip data should come from the existing error-summary request rather than fetching paginated detail rows in the Console. The backend should aggregate model error codes from `swe_tracing_spans.error` using the same source, date, and BBK filters already applied by `/monitor/tracing/error/summary`.

## Scope

- Extend the Monitor error summary response with a model-error-code breakdown.
- Parse model error codes from model error text shaped like `Error code: 404 - {...}`.
- Keep parsing tolerant of string codes even though current known codes are numeric.
- Exclude model error rows whose error text does not contain a recognizable code.
- Show only the top 10 model error codes in the BusinessOverview "模型报错" legend hover.
- Do not add a tooltip for "工具报错".
- Do not change the error detail modal behavior.
- Do not add tests for this change in this workspace unless requested separately.

## Risks

- SQL string parsing support can differ by database engine/version. The implementation should prefer expressions compatible with the repository's current MySQL-style query patterns.
- Existing consumers of `ErrorSummary` should tolerate an additive field, but frontend TypeScript types need to be updated so the Console can use it intentionally.
