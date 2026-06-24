## 1. Runtime Context Formatting

- [x] 1.1 Extend `build_env_context()` to accept the current `source_id`
- [x] 1.2 Replace the existing date-only prompt field with a date-time field that includes seconds, timezone, and weekday
- [x] 1.3 Add explicit missing-value rendering for `source_id` without substituting an implicit default

## 2. Prompt Wiring

- [x] 2.1 Pass the current request `source_id` from runner request context into `build_env_context()`
- [x] 2.2 Verify the final `SWEAgent` SystemPrompt still appends runtime env context after base prompt and multimodal hints

## 3. Regression Coverage

- [x] 3.1 Add unit tests for environment context formatting with explicit `source_id`
- [x] 3.2 Add unit tests for missing `source_id` placeholder behavior
- [x] 3.3 Add or update final SystemPrompt assembly tests to cover the richer runtime metadata
