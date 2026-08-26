# Core Runtime Boundary Refactor Design

## Goal

Reduce the architectural coupling in `AgentRunner`, `SWEAgent`, and
`ProviderManager` while preserving all externally observable behaviour.

The change retains HTTP and CLI contracts, SSE event order, tenant isolation,
Provider JSON layout, session-state layout, retry behaviour, Hook and approval
semantics, and existing workspace lifecycle behaviour.

## Scope and Delivery Shape

The work is three independent, sequential refactors. Each phase is releasable
and reversible on its own; a later phase must not depend on unmerged changes
from a previous phase.

1. Split query lifecycle collaboration out of `AgentRunner`.
2. Split agent-runtime construction out of `SWEAgent`.
3. Split Provider persistence, runtime caching, and catalog operations behind
   the existing `ProviderManager` facade.

No data-store migration, new product feature, API change, or performance
optimisation is included. Any performance work follows separately after the
boundaries and behaviour-characterisation tests are stable.

## Common Design Rules

- Existing public classes and methods remain as compatibility facades.
- New collaborators live next to their current owner, use private module names,
  and expose typed dataclasses or Protocols rather than runtime imports of the
  owner class.
- Behavioural tests are written before moving each execution branch.
- Each phase is a separate commit series and has an independent rollback point.
- A phase may delete old code only after all callers use the new collaborator
  and its focused tests pass.

## Phase 1: Query Lifecycle Boundaries

`AgentRunner` remains the request-facing facade. It continues to own workspace
references, session, chat manager, task tracker, and trace context. Its
`query_handler` and `stream_query` contracts remain unchanged.

The `app/runner/` package gains the following private collaborators:

```text
AgentRunner
  -> query_preflight: pending approval, prompt hook, command-path decision
  -> query_runtime: request values, chat/context directives, MCP/agent setup
  -> query_attempt: retry loop, cancellation, final error handling
  -> turn_lifecycle: stream turn, Goal and Stop completion transitions
  -> session_lifecycle: session load/save and skill-snapshot persistence
  -> query_cleanup: cleanup ordering and timeout policy
```

The existing `_QueryPreflight`, `_QueryRuntimeInputs`, `_QueryRuntime`,
`_TurnPlan`, and retry state dataclasses are the initial boundary contracts.
They may move only after their imports are fully internal to the runner
package. Collaborators receive explicit dependencies and callbacks; they do
not read process-global state beyond the existing context-bound helpers.

### Behavioural invariants

- Approval and Hook short-circuits emit the same terminal response.
- Command routing precedes normal agent execution under the same condition.
- Retry count, backoff, trace status, cancellation conversion, and final error
  presentation are unchanged.
- Normal and Goal turns preserve message and SSE ordering.
- Cleanup retains its current concurrent set: save session, update chat, close
  MCP clients, and end the skill detector, each with the current timeout and
  error rules.

## Phase 2: Agent Runtime Construction Boundaries

`SWEAgent` remains the ReAct runtime: it owns reasoning, acting, memory use in
a turn, media fallback, interruption, and watchdog behaviour. It stops owning
the construction policy for its toolkit, prompt, and MCP registrations.

Introduce a private `agent_runtime_builder` package or module group with:

```text
AgentRuntimeBuilder
  -> ToolCatalogBuilder: built-in, skill, and source tool registration
  -> PromptSnapshotBuilder: workspace prompt files and request injections
  -> McpToolRegistrar: stateful/lazy MCP discovery and registration
  -> AgentRuntimeComponents: model, formatter, toolkit, prompt, memory setup
```

`AgentRunner` continues to pass request-specific values through the existing
agent creation boundary. `AgentRuntimeBuilder` returns components needed by
the constructor, so `SWEAgent` neither reads configuration files to build a
toolkit nor decides how a configured MCP client is registered.

`AgentRequestContext` is introduced as an internal typed model that mirrors
the current request-context keys. During migration it supports conversion to
the existing dictionary, preserving hooks and external tool integrations that
currently consume dictionary keys.

### Behavioural invariants

- Registered tool names, descriptions, schemas, collision behaviour, and
  ordering are unchanged.
- Prompt file selection, heartbeat filtering, model capability hints, Goal and
  Plan additions, and system-prompt refresh semantics are unchanged.
- Lazy MCP discovery stays concurrent; stateful MCP connection/recovery keeps
  current ordering and failure isolation.
- Watchdog, memory compaction, tool guard, and cancellation retain their
  existing lifecycle boundaries.

## Phase 3: Provider Domain Boundaries

`ProviderManager` remains the public compatibility facade and retains its
current tenant-scoped API. Its implementation delegates to three focused
private services:

```text
ProviderManager facade
  -> TenantProviderRepository: tenant paths, atomic JSON reads/writes, locks,
     default/template seeding, and file freshness tokens
  -> ProviderRuntimeCache: per-tenant instances, single-flight startup,
     freshness scheduling, and cache invalidation
  -> ProviderCatalogService: provider CRUD, model activation, model probing,
     and provider-info composition
```

The repository is the only component allowed to know provider file locations.
The cache is the only component owning class-level instance and in-flight
state. The catalog service works on provider models and repository/cache
interfaces, not directly on `Path` objects or process-global maps.

### Behavioural invariants

- Provider file names, permissions, locks, migration/seeding and tenant
  isolation remain unchanged.
- The existing single-flight initialisation and freshness-TTL behaviour remain
  unchanged.
- Provider CRUD, active-model selection, multimodal probing, error handling,
  and async return values remain compatible.
- Existing callers keep importing and calling `ProviderManager`.

## Verification Strategy

Before each extraction, add characterisation tests for the branch being moved.
The mandatory scenarios are normal chat completion, Hook block, approval
resume/deny, command routing, retryable and terminal model failures,
cancellation, Goal lifecycle, session persistence failure, MCP registration
failure, provider initialisation concurrency, provider file refresh, and
tenant isolation.

For each phase, run the focused unit tests first, then the affected runner,
agent, provider, workspace, and tenant-isolation suites. Finally run the
critical runtime-path integration tests. Before every commit, use GitNexus
`detect_changes` to verify that affected symbols and flows match the phase
boundary.

## Non-goals

- Do not alter HTTP endpoints, SSE payloads, CLI command signatures, or
  external configuration schemas.
- Do not move session, chat, or provider persistence to a different storage
  technology.
- Do not alter retry/timeout values, Hook policy, approval policy, or tenant
  scope resolution.
- Do not combine cleanup parallelisation, MCP caching, or other performance
  changes with these structural refactors.
