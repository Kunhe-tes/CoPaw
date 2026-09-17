# Default Agent Hook Console Allows Tenant-Scoped Handler Execution

The Default Agent Profile Hook Console is a dedicated Run Center surface backed by purpose-built APIs rather than the generic Agent API. It deliberately retains the existing tenant-scoped access model: authorized tenant users may configure structured `argv` handlers and manually test a draft handler with real effects. This favors operational self-service over a manager-only gate, so the console must constrain script references to its owned library, apply the configured safety scan, require explicit test confirmation, and emit a redacted structured audit log for every configuration, script, and test action.

## Considered Options

- Extend the generic Agent API — rejected because script ownership, audit, and testing boundaries would be mixed into unrelated Agent lifecycle operations.
- Require a manager/admin role — rejected in favor of the existing tenant-scoped access model.

## Consequences

Manual tests and configured handlers can execute commands, HTTP requests, and prompt handlers with real external effects. Future changes must preserve the controlled script-path boundary, scan policy, confirmation, best-effort structured audit logging, and non-interruption of already-running hooks unless this ADR is explicitly superseded.
