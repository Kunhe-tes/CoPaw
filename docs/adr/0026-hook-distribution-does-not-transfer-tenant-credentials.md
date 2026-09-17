# Hook Distribution Does Not Transfer Tenant Credentials

**Status:** Accepted. An Agent Profile Hook Distribution transfers selected Hook configuration and controlled scripts, but never reads or transfers values from a tenant runtime environment or secret store. Literal Handler headers and command environment values are ordinary Hook configuration and transfer verbatim; Handler references remain literal names and resolve only against each target tenant's own runtime configuration.

## Considered Options

- Copy source tenant runtime values with the Hook — rejected because a Hook distribution must not become a cross-tenant credential-distribution mechanism.
- Reject targets that do not currently resolve every reference — rejected because target credential provisioning remains independent from Hook configuration distribution.

## Consequences

A successfully distributed Hook can still require target-specific environment setup before every handler receives the same runtime values as its source counterpart. Literal configuration may contain sensitive values and is therefore never retained in distribution audit records; values from tenant runtime configuration or secret storage are never a distribution payload.
