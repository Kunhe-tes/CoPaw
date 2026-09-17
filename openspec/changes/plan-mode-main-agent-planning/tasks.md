## 1. Backend Plan Domain And Persistence

- [x] 1.1 Add failing unit tests for Proposed Plan model validation, backend-generated `plan_id`, and required fields.
- [x] 1.2 Add `src/swe/app/plans/` models for Proposed Plans, Plan Interaction Cards, and Plan Review Decisions.
- [x] 1.3 Add failing unit tests for JSON workspace storage under `workspace_dir/plans/<chat_id>/<plan_id>.json`.
- [x] 1.4 Implement a JSON Proposed Plan store with atomic writes, chat-scoped reads, and decision recording.
- [x] 1.5 Add a Plan service that creates plans, records decisions, validates chat ownership, and loads accepted plans by `plan_id`.

## 2. Backend Request State And Metadata Flow

- [x] 2.1 Add failing tests showing `/console/chat` preserves `mode` and `plan_interaction_response` metadata.
- [x] 2.2 Update Console request parsing to carry planning metadata through `native_payload["meta"]` and `AgentRequest.channel_meta`.
- [x] 2.3 Add failing tests for `ChatSpec.meta.plan_mode_enabled` persistence when requests enter, revise, execute, exit, or manually disable Plan Mode.
- [x] 2.4 Update runner/chat-manager integration so request mode resolution and Plan Mode state transitions are persisted consistently.
- [x] 2.5 Implement `exit_plan` short-circuit behavior so valid exit decisions close Plan Mode and do not start a Main Agent run by default.

## 3. Backend Planning Tools

- [x] 3.1 Add failing tests for `ask_plan_clarification` output shapes for `single_choice`, `multi_choice`, and `text`.
- [x] 3.2 Add failing tests for `submit_proposed_plan` persisting a Proposed Plan before emitting Plan Review Card metadata.
- [x] 3.3 Implement `ask_plan_clarification` and `submit_proposed_plan` built-in tools.
- [x] 3.4 Register planning tools for Main Agent in all modes and ensure SubAgents do not emit Plan Interaction Cards.
- [x] 3.5 Add tests that frontend-submitted plan snapshots are ignored and execution uses the persisted plan record.

## 4. Backend Planning Readonly Policy

- [x] 4.1 Add failing tests that Plan Mode toolkit excludes write, edit, static-copy, task-progress, timezone, token-usage, and mutating tools.
- [x] 4.2 Add failing tests that Plan Mode toolkit includes allowed read/search/time/shell tools and readonly delegation when enabled.
- [x] 4.3 Implement Main Agent Planning Readonly Policy toolkit filtering in `SWEAgent._create_toolkit`.
- [x] 4.4 Add failing ToolGuard tests for hard denial of mutating tools, mutating shell, test commands, deployment commands, and migration commands before approvals or hooks.
- [x] 4.5 Implement Plan Mode hard-policy enforcement in `ToolGuardMixin`, including recheck after hook-updated input and approval replay.
- [x] 4.6 Add tests ensuring Plan Mode suppresses `update_task_progress` prompt requirements while normal mode behavior remains unchanged.

## 5. Frontend Plan Mode State And Requests

- [x] 5.1 Add failing frontend tests for Plan Mode toggle initialization from `ChatSpec.meta.plan_mode_enabled`.
- [x] 5.2 Implement the Chat UI Plan Mode toggle and persist changes through the chat API.
- [x] 5.3 Add failing frontend tests for `/plan <text>` enabling Plan Mode and sending stripped text with `mode="plan"`.
- [x] 5.4 Add failing frontend tests for `/plan` alone enabling Plan Mode without starting a model request.
- [x] 5.5 Extend the chat input submission flow so pre-submit logic can inspect and transform input content safely.
- [x] 5.6 Update Console chat fetch and reconnect paths to send explicit `mode` and Plan Interaction Response metadata.

## 6. Frontend Planning Cards

- [x] 6.1 Add failing tests for Planning Clarification Card rendering for single choice, multiple choice, and text input.
- [x] 6.2 Implement Planning Clarification Card rendering and submission as a structured next chat turn.
- [x] 6.3 Add failing tests for Plan Review Card actions: continue modifying, execute, and only exit Plan Mode.
- [x] 6.4 Implement `PlanReviewCard` separately from ToolGuard `ApprovalActionCard`.
- [x] 6.5 Disable or mark Plan Review Cards after a review decision is submitted.
- [x] 6.6 Ensure `revise` keeps Plan Mode, `execute` exits Plan Mode and sends a normal execution turn, and `exit_plan` exits without starting execution.

## 7. Integration And Regression Verification

- [x] 7.1 Add an integration test proving Main Agent cannot mutate files while in Plan Mode.
- [x] 7.2 Add an integration test proving approve/execute restores normal-mode tool ability on the following turn.
- [x] 7.3 Add a regression test proving normal chat behavior is unchanged when Plan Mode is not enabled.
- [x] 7.4 Run targeted backend tests for plans, console request parsing, runner context, toolkit filtering, ToolGuard policy, and SubAgent runtime regressions.
- [x] 7.5 Run targeted frontend tests for Chat page Plan Mode controls and planning cards.
- [x] 7.6 Run `openspec validate plan-mode-main-agent-planning --no-color`.
