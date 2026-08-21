# W+ SOP store directory change

## Goal

Store W+ SOP runtime state at `<agent-workspace>/.sop/wplus-sop.json`
instead of `<agent-workspace>/.copaw/wplus-sop.json`.

## Decisions

- `.sop` is the only active W+ store directory after this change.
- Do not automatically read, copy, move, or delete the legacy `.copaw` file.
  The legacy file may contain a schema-incompatible store and must remain
  available for a separate explicit migration or backup workflow.
- All service, router, Chat entry, and Agent event-tool paths continue to use
  the shared `store_path_for_workspace()` helper.

## Tasks

1. Add a failing path-contract test for `.sop/wplus-sop.json` and for ignoring
   an existing legacy `.copaw/wplus-sop.json`.
2. Change `store_path_for_workspace()` and replace test fixtures that bypass
   the shared helper.
3. Run W+ store/service/router/Chat-entry/tool tests, then the full W+ suite.
4. Run compilation, diff checks, and GitNexus change detection.

## Acceptance criteria

- New W+ entry proposals create `.sop/wplus-sop.json`.
- No W+ runtime path reads or writes `.copaw/wplus-sop.json`.
- Existing legacy files are left untouched.
- W+ tests pass without changing persisted state semantics beyond the path.
