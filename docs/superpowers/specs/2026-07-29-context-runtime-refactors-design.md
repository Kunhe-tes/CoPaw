# Context Runtime Refactors Design

## Goal

Reduce the complexity of the query-runtime and context-reference directive
builders while preserving their externally observable behavior. Correct the
background-task callback annotation so it accepts every value the current
asyncio call sites can produce.

## Scope

- Refactor `AgentRunner._prepare_query_runtime` in
  `src/swe/app/runner/runner.py` into focused private helpers.
- Refactor `build_context_reference_directives` in
  `src/swe/app/runner/context_references.py` into focused validation,
  resolution, and rendering helpers.
- Change `_consume_task_outcome` in `src/swe/app/context_references.py` to
  accept `asyncio.Future[Any]`, which covers both tasks and futures returned
  by `asyncio.ensure_future`.
- Add or extend focused regression tests for the extracted boundaries and the
  accepted future type where a useful executable assertion is available.

## Design

### Query runtime preparation

Keep `_prepare_query_runtime` as the orchestration boundary and preserve its
signature and `_RuntimeStartResult` behavior. Extract helpers for:

1. Preparing request-derived environment context and selected directives.
2. Resolving shared query dependencies (agent configuration, tenant hooks,
   hook overlay, and passthrough headers).
3. Connecting MCP clients, creating the chat, running the session-start hook,
   and returning the existing blocked result when required.
4. Creating and initializing the agent-backed `_QueryRuntime`, including
   skill-detector attachment, confirmed-skill restoration, and declaration
   detection.

The top-level method remains responsible for logging, resource lifetime, and
the existing cleanup-on-error guarantee for connected MCP clients.

### Context-reference directives

Keep `build_context_reference_directives` as the asynchronous public boundary
and preserve ordering, deduplication, maximum-reference handling, and all
validation rules. Extract helpers for:

1. Normalizing and deduplicating raw references.
2. Building the allowed skill-directive lookup.
3. Discovering only the requested MCP tool identities and building their
   availability lookup.
4. Converting each normalized reference into its trusted directive.

Only requested MCP tools continue to trigger discovery; workspace file checks
continue to resolve paths beneath their allowed root before rendering.

### Background task typing

`asyncio.ensure_future` accepts a broad awaitable and its returned value is
typed as an `asyncio.Future`, not necessarily an `asyncio.Task`. The callback
only requires `add_done_callback`, `result`, and cancellation state, all of
which belong to `Future`. Therefore `_consume_task_outcome` will accept
`asyncio.Future[Any]`; its implementation and error handling stay unchanged.

## Error handling and compatibility

The refactor must preserve:

- MCP cleanup if query-runtime initialization raises.
- blocked session-start responses retaining the created chat and MCP clients.
- context-reference ordering and omission of invalid/unavailable references.
- non-blocking observation of cancelled, timed-out, and late background tasks.

No public function signatures, response payloads, directive XML, or security
validation semantics change.

## Verification

Run the focused context-reference and runner hook-runtime tests, then the
project's relevant static type check/lint command. Inspect the final diff and
use GitNexus change detection before any commit.
