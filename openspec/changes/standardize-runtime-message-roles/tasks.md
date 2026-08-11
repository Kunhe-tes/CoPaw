## 1. Establish Role Policy Tests

- [x] 1.1 Run GitNexus upstream impact analysis for each hook message, formatter, session, Provider, and accepted plan symbol before editing, and record any HIGH or CRITICAL risk
- [x] 1.2 Update hook message, ToolGuard hook, STOP hook, formatter, session, and chat API tests to require hook `additionalContext` to remain `system`
- [x] 1.3 Add accepted plan tests that require a paired internal assistant tool call and `tool` result, matching call identifiers, no system prompt injection, and no real tool execution side effects
- [x] 1.4 Update Provider compatibility tests to require requests without `developer` and no developer-to-user retry

## 2. Standardize Hook And Legacy Roles

- [x] 2.1 Change the hook message helper and all hook persistence paths to create plain `system` messages without runtime role mutation
- [x] 2.2 Update model formatters to preserve non-leading hook system messages while retaining the existing handling for unrelated non-leading system messages
- [x] 2.3 Change session loading and chat history conversion to migrate legacy `developer` messages to `system` without restoring or exposing `developer`
- [x] 2.4 Remove developer-specific role constants, metadata restoration paths, and obsolete compatibility helpers

## 3. Inject Accepted Plan As Tool Context

- [x] 3.1 Replace accepted plan system prompt construction with a bounded internal tool-exchange builder that only accepts server plan store data outside Plan Mode
- [x] 3.2 Inject the paired internal assistant tool call and accepted plan `tool` result into the current execution turn without entering Toolkit, ToolGuard, hook, approval, or frontend tool-card flows
- [x] 3.3 Verify OpenAI, Anthropic, and other active formatter paths preserve a protocol-valid accepted plan tool exchange
- [x] 3.4 Remove obsolete accepted-plan-in-system-prompt logic and update associated tests

## 4. Remove Developer Provider Compatibility

- [x] 4.1 Remove OpenAI-compatible Provider detection, downgrade, and retry behavior that exists only for `developer` messages
- [x] 4.2 Add a regression assertion that formatted Provider requests contain only `system`, `user`, `assistant`, and `tool` roles

## 5. Documentation And Verification

- [x] 5.1 Update `analysis/playbook/common-errors.md` and `analysis/playbook/location-paths.md` to document hook system messages, accepted plan tool exchange pairing, and legacy developer-to-system migration
- [x] 5.2 Run targeted pytest suites for hook runtime, ToolGuard hooks, runner hooks, session, chat API, model formatter, Provider compatibility, and Plan Mode
- [x] 5.3 Run the broader non-slow pytest suite and pre-commit checks required for the touched files
- [ ] 5.4 Run `gitnexus_detect_changes()` and confirm affected symbols and execution flows match the proposed scope before commit
