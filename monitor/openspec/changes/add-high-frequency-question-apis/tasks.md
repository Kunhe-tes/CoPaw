## 1. OpenSpec

- [x] 1.1 Add proposal for high-frequency question APIs
- [x] 1.2 Add API and persistence specification
- [x] 1.3 Add strict OpenSpec delta requirements

## 2. Backend Models

- [x] 2.1 Add request and response models for source message query
- [x] 2.2 Add request and response models for result batch save
- [x] 2.3 Add validation for scope, ranks, counts, duplicates, and samples

## 3. Backend Services

- [x] 3.1 Query clean source messages from `swe_tracing_traces`
- [x] 3.2 Enforce completed status and cron-task session exclusion
- [x] 3.3 Enforce 10000 message maximum with explicit error
- [x] 3.4 Save result batches with delete-then-batch-insert transaction

## 4. Routes

- [x] 4.1 Add `POST /monitor/high-frequency-question/messages`
- [x] 4.2 Add `POST /monitor/high-frequency-question/results`
- [x] 4.3 Register the router under monitor's API router

## 5. Verification

- [x] 5.1 Add focused unit tests
- [ ] 5.2 Run the relevant monitor test subset
