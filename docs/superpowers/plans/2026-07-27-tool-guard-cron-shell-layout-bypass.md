# Tool Guard Cron Shell Layout Bypass Fix

**Date:** 2026-07-27

## Problem

The `cron_security` shell rule recognizes single-line commands that begin with
`swe cron create` or `swe cron update`, but misses equivalent commands written
with shell line continuations or after a shell command separator. Those layouts
can reach the same cron mutation while bypassing Tool Guard approval.

## Scope

- Keep the change inside the built-in dangerous-shell rule set.
- Cover both `execute_shell_command` and `start_background_process`.
- Preserve the existing help-command exclusion.
- Do not change cron CLI behavior, shell execution, or generic regex semantics.

## Implementation

1. Add regression coverage in
   `tests/unit/security/test_shell_guard_rules.py` for:
   - `create` and `update`;
   - backslash-newline continuations;
   - `&&` and `;` command chains;
   - both guarded shell tools;
   - benign cron subcommands and direct help requests.
2. Confirm the new mutation-layout test fails against the current rule.
3. Update `cron_security` in
   `src/swe/security/tool_guard/rules/dangerous_shell_commands.yaml` so the
   command token can start at the shell input boundary or after a recognized
   shell separator, without requiring a single-line suffix match.
4. Run the targeted rule tests, the broader Tool Guard tests, and final
   GitNexus change detection before commit.

## Acceptance Criteria

- Every covered cron mutation layout yields exactly one `cron_security`
  finding for foreground and background shell tools.
- `swe cron create --help`, `swe cron update -h`, and non-mutating cron
  subcommands remain unflagged by `cron_security`.
- The change introduces no new dangerous-shell or database-access guard
  failures; unrelated baseline failures remain documented rather than being
  folded into this security fix.
