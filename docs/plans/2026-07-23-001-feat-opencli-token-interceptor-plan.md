---
title: "feat: Inject Runtime Auth Credentials into OpenCLI Shell Commands"
type: feat
status: complete
date: 2026-07-23
---

# feat: Inject Runtime Auth Credentials into OpenCLI Shell Commands

## Summary

Extend the existing shell interceptor so commands whose executable is
`opencli` receive default `--authorization` and `--cookie` arguments resolved
from the current tenant's cron authentication state. Keep explicitly supplied
credentials authoritative per field, fail clearly when a required runtime
credential is unavailable, and never write injected secrets to logs.

## Scope Boundaries

- Reuse `resolve_auth_token_for_execution`; do not change token issuance or
  persistence semantics.
- Apply through the shared shell preparation path so foreground and managed
  background shell execution remain consistent.
- Do not broaden shell-chain parsing beyond the existing `&&` behavior.
- Do not change non-OpenCLI commands or existing `swe cron` interception.

## Implementation Units

### U1. Characterize OpenCLI credential interception behavior

**Goal:** Lock down default authorization and cookie injection, per-field
explicit precedence, tenant scope, missing credentials, expired credentials,
chained commands, and secret-safe logging.

**Files:**

- `tests/unit/agents/tools/test_shell_interceptor.py`

**Execution note:** Add failing tests before production changes.

**Test scenarios:**

- A plain OpenCLI command receives the resolved authorization and cookie using
  the effective tenant identity and current workspace.
- An explicit `--authorization` or `--cookie` is preserved while the missing
  counterpart is resolved and injected.
- Commands that explicitly provide both credentials do not invoke the
  resolver.
- A matching OpenCLI segment inside an `&&` chain is modified without changing
  adjacent commands.
- Missing authentication and expired user information produce a clear
  structured tool failure.
- Logs indicate interception without containing the original or injected
  token.
- Existing `swe cron` behavior remains unchanged.

### U2. Add dynamic credential injection to the shell interceptor

**Goal:** Resolve and inject OpenCLI authorization and cookie values at the
shared pre-execution boundary without exposing them through logs.

**Dependencies:** U1

**Files:**

- `src/swe/agents/tools/shell_interceptor.py`
- `src/swe/agents/tools/shell.py`
- `tests/unit/agents/tools/test_shell_interceptor.py`

**Approach:**

- Detect `opencli` by parsed executable token.
- Resolve credentials with `resolve_auth_token_for_execution` using the
  effective tenant and current workspace contexts.
- Preserve explicitly supplied credentials independently.
- Convert unavailable or expired authentication into canonical shell tool
  failures.
- Log only rule metadata, never command text after secret injection.

**Verification:**

- Targeted interceptor and shell-boundary tests pass.
- Existing cron interceptor tests pass without modification.
- GitNexus reports only the expected shell execution surfaces.

## Risks

- Command-line arguments can be visible to the operating system process list;
  this change prevents application-log disclosure but cannot remove that CLI
  contract risk.
- OpenCLI is not installed in the development environment, so verification is
  limited to command construction and shell integration tests.
