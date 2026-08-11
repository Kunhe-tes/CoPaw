## Context

The existing runtime has a user-facing `AgentRunner` that handles chat
registration, session history, hooks, trace lifecycle, approval replay,
streaming, state save, suggestions, and cleanup. `SWEAgent` already provides
model construction, built-in tools, workspace skills, memory wiring, and
`ToolGuardMixin` interception for sensitive tool calls.

Current code facts that constrain the MVP:

- `SWEAgent._create_toolkit()` registers built-in tool functions from
  `agent_config.tools.builtin_tools`. The concrete built-in names are
  `execute_shell_command`, `read_file`, `write_file`, `edit_file`,
  `grep_search`, `glob_search`, `get_current_time`, `set_user_timezone`,
  `get_token_usage`, `copy_file_to_static`, and `update_task_progress`.
- `SWEAgent._register_skills()` currently loads workspace skills for the
  request channel by default, and skills may add prompt content and tools.
- Existing user-facing agent configuration is tenant/workspace scoped:
  `config.agents.profiles` points at per-agent workspace directories and each
  workspace stores `agent.json`. A SubAgent definition registry should follow
  the same tenant/source/workspace boundary instead of using global mutable
  state.
- `SWEAgent.register_mcp_clients()` registers MCP tools only from clients
  passed to the agent instance.
- `SWEAgent._setup_memory_manager()` can be disabled with
  `enable_memory_manager=False`, otherwise it may attach persistent memory and
  `memory_search`.
- `SWEAgent.reply(..., structured_model=...)` already accepts a Pydantic
  structured-output model.
- `SWEAgent._build_sys_prompt()` currently builds the normal main-agent prompt
  from workspace files and appends `env_context`; this is not enough for an
  independent SubAgent system prompt unless the runtime adds a narrow override
  seam.
- `ToolGuardMixin._acting()` currently runs `PRE_TOOL_USE` hooks before the
  standard guard decision, so SubAgent hard policy must run before hooks and
  approval replay if it is added there.

SubAgents need a narrower contract than a normal chat run. They must execute a
fresh delegated task, keep raw exploration out of the main conversation, obey a
permission policy that cannot exceed the parent context, and return a compact
structured `AgentResult`. The MVP inherits the main agent's model configuration
and only supports readonly shared-workspace SubAgents.

## Goals / Non-Goals

**Goals:**

- Support single-run delegation from a main agent to a named readonly SubAgent.
- Keep SubAgent context fresh: no parent chat history and no persistent memory
  manager.
- Reuse `SWEAgent` model/tool infrastructure and `ToolGuardMixin` enforcement
  instead of building a second model loop.
- Enforce SubAgent tool visibility and authorization at runtime, including
  readonly file and shell protections.
- Disable workspace skills, MCP clients, task-progress tools, timezone/token
  side-effect tools, and persistent memory for MVP SubAgent runs.
- Validate SubAgent output as `AgentResult` and return structured failure,
  blocked, or partial results when validation or execution fails.
- Shape the registry, definition model, and validation path so future
  tenant/workspace-scoped user-defined SubAgents can be registered without
  changing the runtime contract.
- Record SubAgent runs through an interface that can start with local storage
  and later move to a shared store.

**Non-Goals:**

- Plan Mode, Goal Mode, parallel fan-out, result synthesis, or evidence-ledger
  completion evaluation.
- SubAgent-specific model routing or model allowlists.
- Forked parent context.
- Mutating worker SubAgents, sandbox workspace, or git worktree workspace.
- External SubAgent HTTP APIs.
- MySQL or Redis-backed persistence for SubAgent runs.
- MCP server allowlists; MCP tools are disabled by default for this MVP.
- Workspace skill inheritance; SubAgents use only their definition prompt plus
  the delegated task context in this MVP.
- Public CRUD APIs, console UI, import/export, marketplace sharing, or
  cross-tenant broadcast for custom SubAgent definitions. The MVP only defines
  the storage/validation seam and may seed built-ins through code.

## Decisions

### Decision 1: Run SubAgents through a dedicated runtime, not normal chat

`SubAgentRuntime` SHALL directly create a fresh `SWEAgent` instance and invoke
it with a single delegated message. It SHALL NOT call `AgentRunner.query_handler`
or reuse parent chat/session history. It SHALL use a SubAgent-specific system
prompt built from the SubAgent definition prompt, runtime safety contract,
effective policy summary, output contract, and bounded environment summary.
If the current `SWEAgent` only supports appending `env_context` to the normal
main-agent prompt, this change may add a small constructor option such as
`system_prompt_override`; the option defaults to current normal-chat behavior.

Rationale: `AgentRunner.query_handler` is a user-facing lifecycle that includes
chat registration, session load/save, user-visible streaming, and stop hooks.
SubAgents need an internal worker lifecycle with compact structured output.
Direct `SWEAgent` construction preserves model/tool reuse while avoiding main
conversation pollution.

Alternative considered: routing delegation through console chat. This would
reuse more code but would persist SubAgent chatter as user conversation state
and make structured output harder to guarantee.

### Decision 2: Inherit the parent/main agent model

The MVP SHALL use the same model configuration as the parent/main agent. Built-in
SubAgent definitions may declare `model: inherit`, but the runtime does not
implement independent provider, model, temperature, or reasoning routing.

Rationale: the first implementation should prove isolation, permission, and
structured-result semantics before adding cost or latency based model routing.

### Decision 3: Make definitions source-aware and extension-ready

`SubAgentDefinition` SHALL include stable registration metadata:
`name`, `version`, `schema_version`, `source`, `owner_scope`, `enabled`,
`created_at`, `updated_at`, and optional `created_by`. `source` SHALL at least
distinguish `builtin` and future `user` definitions. `owner_scope` SHALL bind
user definitions to the current tenant/source/workspace boundary.

`AgentRegistry` SHALL resolve definitions from ordered providers:

```text
built-in provider
  ↓
tenant/workspace user-definition store
```

The MVP SHALL register the three built-in readonly definitions and provide the
same validation path for stored user definitions. It does not need public CRUD
or UI yet, but it must not hard-code the runtime to built-ins only.

Built-in definitions are immutable and may only be shadowed by user definitions
when an explicit future override policy allows it. Until that policy exists,
duplicate `(name, version)` definitions across sources are rejected rather than
silently overridden.

Rationale: user-defined SubAgents need the same safety checks as built-ins.
Adding source/owner/version metadata now keeps later registration APIs from
changing the runtime, run records, or delegation protocol.

### Decision 4: Validate custom definitions with MVP-safe constraints

Future user-defined SubAgents SHALL use the same `SubAgentDefinition` schema and
the same registry validation as built-ins. During this MVP, any stored custom
definition that is loaded must still satisfy MVP constraints: fresh context,
shared workspace, no memory, no skills, no MCP, no nested delegation, inherited
model, readonly policy, and allowed-tool subset only.

The registry SHALL reject custom definitions that request unsupported isolation,
model routing, mutating tools, unknown built-in tool names, skill tools, MCP
tools, or nested delegation. This keeps future registration extensibility from
weakening the MVP safety boundary.

Rationale: the extension point should be data-driven, but not permission-driven.
Capabilities expand only through explicit future OpenSpec changes.

### Decision 5: Enforce permissions in two layers

The runtime SHALL restrict visible tools by applying a per-run tool allowlist
before creating the SubAgent `SWEAgent`. It SHALL build a copied
`AgentProfileConfig` whose `tools.builtin_tools` enables only the effective
allowlist. `ToolGuardMixin` or an equivalent pre-tool authorization hook SHALL
then enforce parameter-level policy, especially for `execute_shell_command`.

Rationale: hiding write tools is necessary but insufficient because shell is a
mixed read/write tool. Runtime authorization must reject mutating commands,
redirects, and nested delegation even if the model attempts them.

Alternative considered: prompt-only restrictions. This is rejected because a
model instruction cannot guarantee that a tool call is impossible.

### Decision 6: Apply SubAgent hard policy before hooks and approvals

SubAgent hard policy SHALL run before `PRE_TOOL_USE` hooks, approval replay,
and the normal configurable `ToolGuardEngine` decision. A readonly SubAgent
policy denial SHALL return a denied tool result directly and SHALL NOT create a
user approval request.

Rationale: tenant hooks and approval replay are designed for normal chat runs.
They must not widen a SubAgent's effective policy or turn a forbidden readonly
operation into an approvable operation.

### Decision 7: Disable workspace skills and MCP clients for MVP SubAgents

`SubAgentRuntime` SHALL create SubAgent `SWEAgent` instances with
`enable_memory_manager=False`, no MCP clients, no task tracker, and a SubAgent
request context that disables workspace skill loading. If `SWEAgent` has no
existing switch for skill disabling, this change may add a small constructor
option such as `enable_workspace_skills=False`; the option defaults to current
normal-chat behavior.

Rationale: workspace skills can add instructions, hooks, and tools that are not
part of the SubAgent definition. The MVP's safety property depends on the
runtime controlling the whole prompt/tool surface.

### Decision 8: Use existing structured-output support first

`SubAgentRuntime` SHALL call `SWEAgent.reply(..., structured_model=AgentResult)`
when supported by the active model/formatter. The runtime SHALL still validate
the returned content with the `AgentResult` Pydantic model and keep one repair
attempt plus structured fallback for models that return invalid JSON.

Rationale: this reuses existing runtime support and reduces prompt-only schema
fragility without making the design depend solely on provider-native structured
output.

### Decision 9: Keep run storage behind an interface

The MVP SHALL introduce a run-store interface for SubAgent status, spec, policy,
result, and errors. The first implementation SHALL use tenant/workspace-local
JSON under the same app workspace state boundary used for sessions/jobs, with
an in-memory implementation only for tests. It SHALL NOT write run records into
the delegated repository checkout when that differs from app workspace state.

Rationale: multi-instance coordination work is still separate from this change.
An interface keeps this MVP small while preserving a migration path to MySQL,
Redis, or another shared store.

### Decision 10: Return compact structured results only

SubAgents SHALL return `AgentResult` JSON. The runtime SHALL validate the final
assistant output and convert invalid output or runtime failures into structured
`partial`, `blocked`, or `failed` results. Raw logs and long file contents SHALL
not be returned unless allowed by the delegation return policy.

Rationale: the main agent needs decision inputs, not another full transcript.
This preserves the context-isolation value of SubAgents.

## Risks / Trade-offs

- Shell commands can mutate through surprising flags or command composition →
  enforce a conservative allowlist plus denied patterns for readonly SubAgents
  and add focused unit tests.
- Workspace skills can add prompt/tool/hook behavior outside the SubAgent
  definition → disable workspace skills for MVP SubAgent runs and test that
  skill-provided tools are absent.
- Future custom SubAgent registration can accidentally bypass built-in safety
  assumptions → run every definition source through one validator, record
  source/owner/version in runs, reject duplicates and unsupported capabilities,
  and keep custom CRUD/UI outside the MVP.
- Hook approval flow can otherwise run before normal guard decisions → run
  SubAgent hard policy first and test that forbidden calls do not create
  approval requests.
- Direct `SWEAgent` construction may duplicate small parts of runner setup →
  keep runtime construction narrow and reuse shared helpers for environment
  context where possible.
- Normal `SWEAgent` system prompt construction is main-agent-oriented → add a
  minimal prompt override for SubAgents instead of trying to express the
  SubAgent role as appended environment context.
- Tool visibility based on an `AgentProfileConfig` copy can drift from runtime
  policy enforcement → test both registered tools and policy-denied attempted
  calls.
- Local run storage is not cross-pod authoritative → keep external APIs and
  distributed run control out of this MVP and document storage as replaceable.
- SubAgent output may not be valid JSON → retry once with a repair instruction
  or return a runtime-generated structured partial/failed result.

## Migration Plan

1. Add SubAgent modules and tests without registering `delegate_to_subagent`.
2. Add source-aware definition models, registry providers, and definition-store
   interfaces.
3. Register built-in readonly SubAgents and validate them through the same path
   future user definitions will use.
4. Add the minimal `SWEAgent` construction switches needed for SubAgent-safe
   tool and skill surfaces, preserving normal-chat defaults.
5. Add runtime policy enforcement for SubAgent tool calls before hooks and
   approvals.
6. Register `delegate_to_subagent` only for main-agent contexts.
7. Roll back by disabling or removing `delegate_to_subagent`; normal chat runs
   remain unchanged because the SubAgent runtime is not on the default chat path.

## Resolved Scope Boundaries

- First run store: tenant/workspace-local JSON through a replaceable
  `SubAgentRunStore`; in-memory is test-only.
- Test execution: readonly SubAgents may discover test files and recommend
  commands, but they SHALL NOT run test commands that can create caches,
  coverage files, snapshots, or other workspace writes. Actual test execution
  waits for a later sandbox/test policy.
- Hook/tracing identity: SubAgent runs use an explicit request-context marker
  such as `agent_role=subagent` plus `subagent_run_id`. They may also use
  `channel=subagent` for trace readability, but authorization MUST rely on the
  explicit role/run fields rather than channel text.
- Custom definition extension mode: model, validation, registry provider, and
  local store interfaces are in scope; public APIs, UI, marketplace import,
  cross-tenant sharing, mutable custom workers, and custom model routing are
  out of scope for this MVP.
