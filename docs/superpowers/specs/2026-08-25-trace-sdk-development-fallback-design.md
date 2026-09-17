# Trace SDK Development Fallback Design

## Goal

Allow a developer to run the SWE backend without the private
`LR34.05-AgentTraceSDK` distribution, while retaining the existing production
contract: a missing SDK fails startup unless development fallback is explicitly
enabled.

## Scope and non-goals

- Add one internal compatibility module that owns all AgentTraceSDK imports.
- Use the real SDK whenever it is importable.
- Enable a no-op implementation only when `SWE_ALLOW_MISSING_TRACE_SDK=true`
  and the real SDK cannot be imported.
- Replace the six production direct SDK import sites with the compatibility
  module.
- Do not alter trace topology, SDK configuration, exporter behavior, or the
  private package declaration in `pyproject.toml`.
- Do not expose this fallback in production deployment configuration.

## Design

The compatibility module attempts the real import first.  If it is absent and
the opt-in environment variable is true, it exposes the small API used by SWE:
`SpanKind`, `TraceFields`, `global_tracer`, `chat_traced`,
`execute_tool_traced`, and `shutdown_global_tracer`.

The no-op tracer returns an asynchronous context manager whose `set_attribute`
method discards values.  The two decorators preserve the wrapped async
function.  Consequently, existing runner, agent, tool-guard, and lifecycle
code executes unchanged, but emits no AgentTraceSDK data.  With the variable
absent or false, the original `ModuleNotFoundError` is re-raised, preserving
the fail-fast production behavior.

## Verification

1. Add a regression test proving that importing the FastAPI app succeeds in a
   subprocess with no `trace_sdk` installed and
   `SWE_ALLOW_MISSING_TRACE_SDK=true`.
2. Prove the same import fails with the variable unset.
3. Run the existing AgentTraceSDK tests with their test-only fake on
   `PYTHONPATH`; they must still validate the real SDK call contract.
4. Run a development startup/import smoke test using the documented opt-in
   command.

## Developer operation

Start locally without the private package using:

```bash
SWE_ALLOW_MISSING_TRACE_SDK=true swe app
```

This setting intentionally disables only AgentTraceSDK instrumentation; it
does not disable SWE's existing tracing manager.
