# W+ question event contract fix

## Problem

After the platform persists `stage_queue_confirmed` and enters `GeneratingQuestions`, the Agent can emit `stage_queue_confirmed` again. The state machine correctly rejects that event, but the runtime prompt does not tell the Agent that `question_batch` is the only business event accepted in this state.

## Scope

- Derive the required Agent event from the server-selected target state.
- Put the target state and required event in the Agent command envelope.
- Add a strict `GeneratingQuestions -> question_batch` output contract that explicitly forbids replaying `stage_queue_confirmed`.
- Keep server-side validation fail-closed, but include the allowed event names in rejection messages so the Agent can self-correct.
- Cover initial queue confirmation, later non-final stage confirmation, resume, and retry.

## Non-goals

- Do not accept or silently translate invalid duplicate events.
- Do not move state ownership into the skill or model.
- Do not change routes, persistence schemas, or the workspace UI.

## Implementation

1. Add failing runtime tests for the `GeneratingQuestions` contract and state forwarding.
2. Add failing service tests for all commands that start or resume question generation and for the corrective validation error.
3. Extend `build_wplus_command_text` and `start_wplus_chat_turn` with the target state, derive the required event, and render the strict contract.
4. Pass the target state from `WPlusSopService` whenever it starts an Agent turn.
5. Improve invalid-event diagnostics without weakening state validation.

## Verification

- Run focused runtime and service tests.
- Run the full W+ backend unit suite and tool tests.
- Run lint/static checks for touched Python files and `git diff --check`.
- Review the final diff for correctness, contract compliance, maintainability, and test coverage.
