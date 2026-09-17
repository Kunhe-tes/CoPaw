## 1. Backend Summary Data

- [x] 1.1 Add a response model item for model error code counts.
- [x] 1.2 Extend `ErrorSummary` with `model_error_codes`.
- [x] 1.3 Aggregate model error codes in `TracingQueryService.get_error_summary` using the existing source/date/BBK filters.
- [x] 1.4 Parse codes after `Error code:` and before the next whitespace or delimiter, supporting numeric and string codes.
- [x] 1.5 Exclude model error rows without a recognizable error code from the breakdown.
- [x] 1.6 Limit the backend breakdown to the top 10 by count.

## 2. Console UI

- [x] 2.1 Update the `ErrorSummary` TypeScript type with `model_error_codes`.
- [x] 2.2 Add a tooltip only to the "模型报错" legend label in BusinessOverview.
- [x] 2.3 Render code counts as `404: 3个` style rows.
- [x] 2.4 Show an empty-state tooltip copy only if `model_errors > 0` but no codes are parsed.
- [x] 2.5 Reuse the page's existing tooltip styling patterns and avoid changing the detail modal.

## 3. Verification

- [x] 3.1 Review the changed backend query for source/date/BBK filter parity with current summary counts.
- [x] 3.2 Review the Console diff for targeted UI scope.
- [x] 3.3 Defer runtime tests to the internal environment per request.
