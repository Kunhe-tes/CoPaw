# Selected Expert Reliability Implementation Plan

**Goal:** Keep a selected expert's turn tied to its own run until a verified terminal outcome or an explicit failure.

**Architecture:** Preserve the guarded start and add one guarded internal, run-bound wait. That wait reads only the owned run and uses the persisted effective budget and creation time for its deadline. The selected-expert control path must reserve the transitions needed to process the result outside the model reasoning iteration budget. Keep ordinary background tools and expert-main mode unchanged.

**Tech Stack:** Python 3.12, asyncio, AgentScope, pytest.

## Files

- `src/swe/agents/tools/subagent_background.py`: target-only bounded wait and start identity registration.
- `src/swe/agents/tool_guard_mixin.py`: guarded internal wait routing, safe failure and timeout handling.
- `src/swe/agents/react_agent.py`: registration, bounded forced-control continuation, cancellation.
- `tests/unit/subagents/test_chat_runtime_access.py`: ownership, wait and failure tests.
- `tests/unit/subagents/test_react_agent_and_guard_integration.py`: forced control and actual message tests.
- `tests/unit/subagents/test_background_supervisor.py`: startup/cancellation race tests where supervisor ownership is established.
- `analysis/playbook/common-errors.md`: operational behavior and verification entry.

## Work sequence

1. Add failing tests demonstrating historical terminal runs do not cause a target-only wait to return; a foreign run is never read; absent, invalid and transiently unavailable records terminate or recover within a fixed retry budget. Run each test before implementing. Implement an internal callable with no caller-controlled run ID, reading `selected_expert_run_id` from server request context and using `read_chat_run_record` plus safe supervisor reaping. Return the existing compact result for the target only.
2. Add failing tests for one wait per selected run, actual AgentScope text block output, failure/denial, and `max_iters=1`. Replace repeated wait/get replay with one guarded internal wait. Reserve the forced start/wait/final-result control transitions independently of model iterations without changing ordinary chat iteration behavior. Tests must demonstrate no free-form Main Agent summary while the selected run is still active.
3. Add failing tests for cancellation during start, waiting, and race with terminal completion. Persist run identity as soon as ownership is established; use the existing chat/turn cancellation mechanism when identity is not yet returned. On timeout or cancellation, use bounded cleanup; report uncertain status if the owner cannot confirm cancellation. Never retry a start.
4. Derive an absolute deadline from persisted `created_at` and `effective_budget.timeout_ms` plus a fixed cleanup grace, capped by any existing request deadline. Test no reset across retries, timeout, and generic tool hard-timeout interaction. Restrict the timeout exception to the server-forced internal call and retain Pre/Post hooks and guard behavior.
5. Cover start rejection classes with safe user-facing categories, verify no raw exception or secret is exposed, and document operational investigation. Run all targeted subagent, guard and expert-main tests, then `git diff --check` and relevant pre-commit checks.

## Critical review before implementation

`ReActAgent.reply` counts each forced start and wait as an iteration, and calls `_summarizing` immediately after the final one. Merely collapsing wait calls is insufficient when `max_iters=1`; implementation must explicitly handle the forced control transitions, with a full-loop regression test. `BackgroundSubAgentSupervisor.wait_for_run` is unbounded and process-local, so it cannot be used as the cross-instance deadline mechanism. The server must keep the current request's exact tenant/agent/chat/session scope for all reads and cancellation.

## Completion Record

- Implemented the run-bound internal wait, persisted run identity, bounded timeout and cancellation handling, and selected-expert approval replay metadata.
- Preserved ordinary `wait_subagent` behavior and prevented approval replay from starting a second expert.
- Verification: 505 targeted tests passed, including Hook approval replay, transient reap failures, and cancellation during the first reap. Black (line length 79), pre-commit, and `git diff --check` pass.
