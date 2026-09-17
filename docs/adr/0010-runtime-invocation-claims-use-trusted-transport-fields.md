# Runtime invocation claims use trusted transport fields

Swe will pass Runtime Invocation Claims across MCP HTTP, MCP stdio, Built-in Shell Execution, hook HTTP, and hook command boundaries using transport-native fields rather than signed credentials. The claims are intended for already trusted invocation channels: MCP HTTP receives canonical `x-swe-*` headers plus existing compact aliases, other HTTP handlers receive only canonical headers, and subprocess boundaries receive canonical `SWE_*` environment variables. Runtime-owned claim names override tenant env, handler config, client config, and passthrough values so the receiver sees Swe's current session, trace, tenant, source, and runtime scope claims when those values exist.

**Considered Options**

- Signed Runtime Invocation Credentials: rejected because the current requirement is trusted in-process or configured integration propagation, not independently verifiable delegation to arbitrary receivers.
- Bare per-boundary fields without reserved ownership: rejected because configured headers or env values could spoof the claims before Swe writes the final invocation context.

**Consequences**

Receivers must treat these claims as authorization inputs only when they already trust the invocation channel. The claims are not portable credentials, and absent session or trace values are omitted rather than synthesized.
