# Retire the obsolete voice SOP entry

## Goal

Remove the voice-recorder entry that produces an obsolete `@wplus-sop-miner`
prompt, while retaining voice transcription and protecting console chat identity
validation with focused regression tests.

## Scope

- Remove the voice recorder's "生成SOP" control and its prompt-building helper.
- Remove the helper's tests with the retired behaviour.
- Add console chat tests that reject a mismatched authenticated sender and a
  mismatched authenticated Agent/workspace pair with HTTP 403.

## Non-goals

- Do not restore or replace the reverted W+ SOP workflow.
- Do not change normal voice transcription, chat creation, reconnect, or
  console identity-validation behaviour.
- Do not alter pre-existing uncommitted worktree changes.

## Design

The voice recorder continues to append transcribed text through its existing
transcription-success callback. Its SOP-specific action and prompt helper are
removed so the UI cannot emit a mention for a deleted skill.

The console tests move the two still-required authentication boundaries into a
surviving console chat test module. Each test invokes the actual `/console/chat`
route and asserts HTTP 403 before a chat or task run is created.

## Verification

- Run the affected voice-recorder tests and confirm the obsolete action is no
  longer rendered.
- Run the focused console chat tests and confirm both 403 cases.
- Run the broader touched frontend and backend test files.
