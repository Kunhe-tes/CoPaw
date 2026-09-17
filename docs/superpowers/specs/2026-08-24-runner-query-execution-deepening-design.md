# Runner Query Execution Deepening Design

## Goal

Reduce `src/swe/app/runner/runner.py` from mixed request/lifecycle implementation into an AgentScope compatibility facade that delegates one complete query to a deep `QueryExecution` Module.

The refactor preserves HTTP and CLI contracts, `query_handler` and `stream_query`, SSE ordering and `last`, trace identity, approval, Hook, Stop, Goal, session persistence, tenant isolation, Source Template rules, retry, and MCP cleanup.

## Decision

`QueryExecution` is the only business Interface for a complete query. `AgentRunner` remains the framework Adapter and composition root; it owns AgentScope-facing entry points, workspace/session references, and framework output adaptation.

```text
AgentScope / router / CLI
  -> AgentRunner facade
  -> QueryExecution.stream(QueryInvocation)
  -> ordered QueryFrame stream
  -> AgentRunner framework adaptation
```

```python
@dataclass(frozen=True)
class QueryInvocation:
    request: AgentRequest
    msgs: tuple[Any, ...]

@dataclass(frozen=True)
class QueryFrame:
    message: Msg
    last: bool

class QueryExecution:
    async def stream(self, invocation: QueryInvocation) -> AsyncIterator[QueryFrame]: ...
```

`QueryExecution` is request-stateless. Each invocation creates an internal `QueryRunState`; request metadata updates remain compatible with the existing behavior.

## Module Structure

```text
src/swe/app/runner/
├── runner.py                         # facade, framework Adapter, composition root
├── query_execution/
│   ├── __init__.py                   # QueryExecution / QueryInvocation exports
│   ├── contracts.py                  # value objects and QueryRunState
│   ├── execution.py                  # retry, exception conversion, finally ordering
│   ├── admission.py                  # approval, prompt Hook, command decision
│   ├── activation.py                 # provider/chat/hook/MCP/SWEAgent activation
│   ├── continuation.py               # Agent turn, Stop, Goal, follow-up, timeout
│   ├── session_state.py              # state load/save and skill snapshot continuity
│   ├── observability.py              # trace, title, failure dump, output indexing
│   └── adapters.py                   # live and fake Adapter construction
├── command_dispatch.py               # existing command implementation remains
└── ...
```

The package is one deep Module: its files are internal implementation detail, not independently callable query phases. Callers must not compose approval, activation, retry, Goal completion, or cleanup.

## Fixed Lifecycle

1. Derive query/session/user scope from the request.
2. Resolve pending approval. A denial emits its terminal frame before existing denial-memory cleanup.
3. Run `USER_PROMPT_SUBMIT`. A blocking Hook emits a terminal frame and creates no chat, Agent, or MCP resource.
4. For an eligible command, start/end its trace around the existing command stream. An approval-consumed request keeps the current command-bypass rule.
5. For a normal query, start trace and execute the configured retry loop.
6. Each attempt refreshes the tenant Provider, activates chat/context/MCP/Agent, restores session state, refreshes the session skill snapshot, then streams the Agent turn.
7. Continue through existing Goal steering, review, finalization, Stop gate, and bounded automatic follow-up behavior.
8. Persist observability and session-skill changes under their current conditions.
9. In `finally`, restore context variables and await the current concurrent cleanup set: session state, chat update, MCP close, and skill-detector end. Preserve `asyncio.gather(return_exceptions=True)` and post-gather error propagation.

`RuntimeLease` is internal ownership for both normal runtime and `SESSION_START`-blocked startup, so every attempt releases the chat and MCP resources it created.

## Seams and Adapters

The existing wide `QueryAttemptOwner`, `TurnLifecycleOwner`, and related Protocols are temporary migration aids. Once their logic moves behind `QueryExecution`, they are deleted.

Only these real seams have live and fake Adapters:

- `QueryRuntimeAdapter`: provider refresh, chat/context/MCP activation, Agent construction, blocked-start disposal.
- `QueryStateAdapter`: session restore/save, chat update, skill-snapshot persistence.
- `QueryObservationAdapter`: trace lifecycle, title creation, model failure details, output indexing.

Approval, Hook, Goal, Stop, and command logic use existing domain Modules directly inside the implementation. A generic port or event bus is rejected because it would hide ordering in a shallow Interface.

## Compatibility Invariants

- `AgentRunner.query_handler` and `AgentRunner.stream_query` keep their current call and return shapes.
- Output is neither buffered nor reordered: every message, terminal frame, trace id, and `last` value remains in its existing order.
- Stop remains the sole completion Hook; Goal completion is not a second completion path.
- A query consumes an established tenant scope; it never performs Tenant Bootstrap or Source Template Provisioning.
- Retry notices precede the subsequent attempt; cancellation retains current trace and interruption behavior; final model failures retain the current Console projection.
- Normal and blocked startup close only their own MCP clients. All cleanup tasks finish before a current cleanup exception is surfaced.

## Migration and Verification

1. Add frame-sequence characterization tests for approval, Hook block, command, retry exhaustion, Stop continuation, Goal continuation, cancellation, blocked activation, session-skill freshness, and MCP cleanup.
2. Add contracts plus facade delegation through a live Adapter that calls current code; prove output equivalence in focused tests.
3. Move admission and observability; delete a legacy `AgentRunner` helper only after its Interface test passes.
4. Move runtime activation, session continuity, attempt/finally ownership; introduce `RuntimeLease` and test normal plus blocked-start cleanup.
5. Move continuation as one unit; delete the wide owner Protocols and forwarding helpers.
6. Run focused runner, workspace/tenant, and critical runtime integration tests. Before every commit, use GitNexus `detect_changes`.

The Interface is the test surface. Tests assert invocation, ordered frames, durability effects, and resource release through `QueryExecution`; they do not mock private `AgentRunner._prepare_*` methods. The deletion test passes only when removing a legacy forwarder does not redistribute behavior into callers.

## Non-goals

- No changes to request payloads, SSE schema, routes, CLI arguments, or persistence formats.
- No changes to retry/timeout values, Hook, approval, Goal policy, or tenant resolution.
- No workflow engine, plugin/event bus, configurable phase order, Provider refactor, `SWEAgent` refactor, or frontend work.
