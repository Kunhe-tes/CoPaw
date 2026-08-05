## 1. OpenSpec

- [x] 1.1 Add proposal, design, and delta spec for task flow behavior
- [x] 1.2 Validate the OpenSpec change

## 2. Backend Models

- [x] 2.1 Add task submission, prewarm, topic, and result query response models
- [x] 2.2 Add validation for `source_id`, date ranges, and 7-day maximum

## 3. Backend Service

- [x] 3.1 Normalize source/date/scope request criteria
- [x] 3.2 Query 24-hour reusable successful results
- [x] 3.3 Insert `swe_async_tasks` running records
- [x] 3.4 Dispatch the configured workflow in a background task
- [x] 3.5 Mark tasks `succeeded` or `failed` after workflow completion
- [x] 3.6 Query latest available or stale successful results

## 4. Routes

- [x] 4.1 Add `POST /monitor/high-frequency-question/tasks`
- [x] 4.2 Add `POST /monitor/high-frequency-question/prewarm`
- [x] 4.3 Add `GET /monitor/high-frequency-question/results`
- [x] 4.4 Resolve interactive `source_id` from `X-Source-Id`

## 5. Console UI

- [x] 5.1 Add user-message page high-frequency question modal entry
- [x] 5.2 Query cached results before explicit task submission
- [x] 5.3 Submit generation task from empty state and poll async task status

## 6. Verification

- [x] 6.1 Add focused unit tests for cache hit, task creation, workflow update,
      and result query states
- [x] 6.2 Run syntax checks and available focused tests
