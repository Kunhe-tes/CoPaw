# Agent Trace `source_id` Integration Design

## Goal

Adapt SWE to Agent Trace SDK 0.1.9's required `TraceFields.source_id` field.
Every non-scheduled interactive Agent Trace root span must export the source
identity already used by SWE's request and tenant-isolation model.

## Scope

- Add `source_id` when `AgentRunner.query_handler` creates the `agent.run`
  SDK root span.
- Update SWE's local Agent Trace SDK fallback and test-only SDK fake to match
  the six-field `TraceFields` contract.
- Require Agent Trace SDK 0.1.9 or later in the Python dependency declaration.
- Extend the focused Agent Trace SDK tests.

## Non-goals

- Do not introduce a new request, HTTP header, or API field. SWE already
  carries the source identity on `request.source_id` or `channel_meta`.
- Do not change source-scoped tenant resolution, request context, legacy SWE
  tracing, or trace topology.
- Do not enable Agent Trace SDK tracing for scheduled requests; they currently
  intentionally skip the SDK root span.
- Do not add trace-header propagation for outbound calls as part of this
  change.

## Source Identity Contract

The value has the same meaning as the existing source-scoped isolation key,
not the transport/channel name. Resolve it using the existing
`_request_source_id(request)` helper:

```text
request.source_id
  -> request.channel_meta["source_id"]
  -> "default"
```

The final value is passed as `TraceFields.source_id` on the `agent.run` root
span. `"default"` is the confirmed fallback for requests with no supplied
source, so the SDK's non-empty-string requirement is always met. Child spans
(`agent.admission`, `agent.attempt`, model, and tool spans) remain unchanged;
they inherit the root trace fields through the SDK context.

## Design

### Root-span construction

`AgentRunner.query_handler` is the only production site that constructs
`TraceFields`. It already guards root-span creation on required request and
agent values. Add `source_id=_request_source_id(request)` to that constructor.
No additional guard is needed because the helper provides the non-empty
`"default"` fallback.

This is deliberately a direct use of the existing helper. A new trace-fields
factory would currently wrap a single construction site without adding reuse
or reducing risk.

### SDK contract alignment

The real SDK package must be declared as `LR34.05-AgentTraceSDK>=0.1.9`, the
documented version that includes `source_id`. SWE's no-op compatibility
`TraceFields` dataclass and the test-only fake must add a required
`source_id: str` field in the same position as the SDK contract. Existing
tests that instantiate the fake directly must pass the sixth value.

The fallback remains no-op: it retains the type contract while emitting no
Agent Trace SDK data when explicitly enabled for local development.

## Error Handling and Compatibility

- A supplied `request.source_id` remains authoritative over `channel_meta`.
- Missing or empty request values are represented as `"default"`, consistent
  with the current source-resolution helper.
- Existing scheduled requests continue to create no SDK root span and therefore
  have no SDK `source_id` requirement.
- No malformed-source recovery is added here; source validation and isolation
  semantics remain owned by the existing request/context layer.

## Verification

1. Update the root-span test to supply a source ID and assert the exported
   trace field is identical.
2. Add a no-source case that asserts `"default"` is exported.
3. Add or extend a precedence case proving `request.source_id` wins over
   `channel_meta["source_id"]`.
4. Update the child-span tests' fake `TraceFields` construction and retain
   their parent/child assertions.
5. Run:

   ```bash
   venv/bin/python -m pytest tests/unit/app/test_agent_trace_sdk.py
   venv/bin/python -m pytest tests/unit/tracing/test_agent_trace_sdk_fallback.py
   ```

## Risk

GitNexus classifies `AgentRunner.query_handler` as CRITICAL because it has 51
direct callers. The change is limited to one additional root-span metadata
field and does not alter query execution, response streaming, or source
resolution. Focused root-span and child-span tests protect the SDK contract.
