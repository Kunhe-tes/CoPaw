## Why

Plan Mode needs to become an explicit, user-visible planning state for the Main Agent, with reduced permissions and structured user review before execution resumes. The current chat pipeline does not preserve planning metadata end to end, does not persist Proposed Plans, and conflates plan approval semantics with existing tool-guard approval UI.

## What Changes

- Add explicit per-chat Plan Mode state stored in `ChatSpec.meta.plan_mode_enabled`.
- Add Console request metadata passthrough for `mode`, `plan_interaction_response`, and related planning fields.
- Add a Planning Readonly Policy for the Main Agent in Plan Mode that filters unavailable tools from the toolkit and hard-denies forbidden tool calls.
- Add Main Agent planning interaction tools:
  - `ask_plan_clarification` for `single_choice`, `multi_choice`, and `text` clarification cards.
  - `submit_proposed_plan` for Proposed Plan review cards.
- Persist Proposed Plans under the corresponding tenant Agent workspace `plans/` directory, using backend-generated `plan_id` values.
- Add Plan Review Decision handling for:
  - `revise`: continue modifying the plan and keep Plan Mode enabled.
  - `execute`: execute the persisted plan and exit Plan Mode.
  - `exit_plan`: exit Plan Mode without executing the plan.
- Add frontend Plan Mode toggle, `/plan` shortcut, Planning Clarification Card, and Plan Review Card rendering.
- Preserve the existing synchronous `delegate_to_subagent` runtime and readonly delegation rules; do not add automatic plan-researcher chaining or async SubAgent run APIs in this change.

## Capabilities

### New Capabilities
- `plan-mode-main-agent-planning`: Explicit Plan Mode state, Main Agent planning permissions, planning interaction cards, persisted Proposed Plans, and plan review decision flow.

### Modified Capabilities

None.

## Impact

- Backend Console request parsing and channel metadata forwarding.
- Chat metadata persistence through `ChatSpec.meta`.
- `AgentRunner` request context construction.
- `SWEAgent` toolkit registration and system prompt construction.
- `ToolGuardMixin` hard-policy enforcement for Main Agent Plan Mode.
- New plan domain package for Proposed Plan models, JSON workspace store, service, and tools.
- Frontend Chat page request construction, session metadata handling, sender controls, plan interaction card rendering, and tests.
- Test coverage across backend unit tests, frontend component tests, and integration tests ensuring Plan Mode cannot mutate workspace state.
