# Swe Agent Runtime

This context defines the domain language for Swe's agent orchestration runtime, especially how the main agent coordinates SubAgent work.

## Language

**Tenant Bootstrap**:
The creation or repair of one tenant scope's minimum runnable directory state, including its default Agent Profile and required workspace assets. A Tenant Bootstrap completes only when that scope can load its Default Agent Profile.
_Avoid_: directory creation, partial initialization, workspace startup

**Tenant Bootstrap Recovery**:
The repair of an incomplete or unusable Tenant Bootstrap into its minimum runnable state. Its temporary rollback backup is removed immediately after successful recovery and retained when recovery fails; it is distinct from a first Tenant Bootstrap because it begins with an existing tenant scope.
_Avoid_: silent reset, tenant recreation, best-effort startup

**Tenant Bootstrap Lock**:
The cross-instance exclusive ownership of one Tenant Bootstrap, keyed by that tenant scope's effective storage identity. It prevents two application instances from initializing or recovering the same tenant scope concurrently and rejects bootstrap when this lock cannot be used.
_Avoid_: process-local bootstrap lock, logical-tenant lock, global initialization lock

**Tenant Bootstrap Readiness**:
The verified condition that a tenant scope's required configuration and Default Agent Profile assets are individually valid and mutually consistent. A ready-marker file may describe this condition but cannot establish it by itself.
_Avoid_: file-exists check, marker-only readiness, directory-present check

**Tenant Staging Artifact**:
A temporary file created within a tenant scope before an atomic replacement of its intended target. It is not tenant workspace content and must not be considered a configuration or an agent asset; artifacts left by abrupt process termination require explicit recovery or manual removal.
_Avoid_: workspace file, configuration file, recoverable user document

**Source Template**:
The explicitly provisioned and ready `default_<source_id>` tenant-scope asset used as the initialization source for tenants entering through one source system. A Source Template is distinct from both the global `default` template and an ordinary tenant scope.
_Avoid_: source tenant, default tenant, per-request configuration

**Source Template Provisioning**:
The privileged internal or CLI operation that creates or repairs a Source Template before tenant requests may consume it. It never force-overwrites a ready Source Template, fails without creating a partial template when the global default template is not ready, and ordinary tenant requests cannot initiate it.
_Avoid_: lazy template creation, tenant self-service initialization, request-time template repair

**SubAgent Definition**:
A named, versioned worker profile that describes what kind of delegated work a SubAgent can perform. One **SubAgent Definition** can be used by many **SubAgent Runs**.
_Avoid_: custom subagent, subagent template, agent config

**Run-scoped SubAgent Definition**:
A temporary **SubAgent Definition** supplied by the Main Agent for one **SubAgent Run**. It is validated like other SubAgent Definitions but is not stored for reuse, versioned as a reusable profile, or visible as a long-lived registry entry.
_Avoid_: persistent custom subagent, saved worker profile

**SubAgent Definition Source**:
The audit and launch-snapshot origin of a **SubAgent Definition**. Its values are `builtin`, `agent_owned`, `skill_owned`, and `run_scoped`; they distinguish lifecycle ownership without changing exact-name selection.
_Avoid_: generic stored source, user source, customized source

**Stored SubAgent Definition**:
A reusable **SubAgent Definition** available through the definition registry across more than one **SubAgent Run**. Stored definitions may be built-in or user-owned, but user-owned persistence and CRUD are separate from run-scoped delegation.
_Avoid_: temporary subagent, inline worker profile

**Built-in SubAgent Definition**:
A fixed reusable **Stored SubAgent Definition** supplied by the application. It remains available independently of the expert configuration center and cannot be created, edited, enabled, disabled, or deleted there.
_Avoid_: Agent-owned Definition, Skill-owned Definition, configurable default expert

**Agent-owned Stored SubAgent Definition**:
A reusable **Stored SubAgent Definition** configured in one Agent Profile's expert catalog. It is available only to that Agent Profile while enabled and is independent of any Skill lifecycle.
_Avoid_: Skill subagent, tenant-shared definition, temporary subagent

**Agent-owned Definition Package**:
One `agents/<definition-id>.toml` file in an Agent Profile's workspace expert catalog. Its stable filename-derived **Agent-owned Definition ID** is independent of the editable unqualified `name`; it declares one **Agent-owned Stored SubAgent Definition** and is not packaged, distributed, or enabled as a Skill.
_Avoid_: Skill-owned Definition Package, definition-store JSON record, tenant-shared configuration

**Agent-owned Definition ID**:
The stable opaque identifier represented by an Agent-owned Definition Package's filename. It is used for management, optimistic concurrency, and audit linkage; the Main Agent selects the Definition by its editable `name`, never by this ID.
_Avoid_: runtime SubAgent Name, filename-derived display name, mutable name alias

**Agent-owned SubAgent Name**:
The unqualified, Agent-unique `name` of an **Agent-owned Stored SubAgent Definition**. It cannot use a Skill qualifier or shadow a built-in Definition, while a Skill-owned Definition may share its local name through its distinct **Skill-qualified SubAgent Name**.
_Avoid_: Skill-qualified name, filename-derived fallback, built-in override

**Agent-owned Definition Lifecycle**:
The separate creation, enablement, disablement, and deletion states of an **Agent-owned Stored SubAgent Definition**. Creation produces a disabled Definition; only an enabled Definition is loaded for a later Main Agent turn, and changing the catalog does not interrupt an already launched SubAgent Run.
_Avoid_: file-exists-is-enabled, hot-reload lifecycle, run cancellation

**Skill-owned Stored SubAgent Definition**:
A reusable **SubAgent Definition** packaged by one Skill and available for new **SubAgent Runs** only while its owning Skill is enabled in the target Agent's Skill Runtime View. Disabling or deleting that Skill prevents new runs without interrupting runs that already captured the definition; updates apply to subsequent Main Agent runs.
_Avoid_: skill subagent, independent skill agent, user-owned stored definition

**Skill-owned Definition Package**:
The `agents/<agent-name>.toml` file within a Skill package that declares one **Skill-owned Stored SubAgent Definition**. The package is distributed, scanned, and versioned together with its owning Skill.
_Avoid_: inline SKILL.md agent, shared definition-store record, agent directory manifest

**Declared SubAgent Dependency Set**:
The explicit Skill dependency names, plus an optional MCP restriction, in a **Skill-owned Definition Package**. Skills are the sole optional Skill capabilities eligible to load; when `mcps` is present, it is the sole MCP capability set eligible to load. The owning Skill controls the Definition lifecycle but is not implicitly added as a worker capability.
_Avoid_: implicit owning-skill injection, inherited workspace skills, implicit Skill discovery

**Declared SubAgent Skill Capability**:
One available Skill in an **Effective SubAgent Dependency Set** that the worker registers through the ordinary Skill Toolkit path, including that Skill's normal prompt and Skill-tool registration behavior. A Definition instruction does not inline the Skill document.
_Avoid_: embedded SKILL.md body, bypassed Skill Toolkit registration, all-workspace Skill tools

**Effective SubAgent Dependency Set**:
The available and authorized dependency subset for one **SubAgent Run**. Skills resolve only from declared names in the parent Agent's enabled Skill Runtime View; MCPs resolve from declared names when `mcps` is present, including an empty list that disables all MCPs, otherwise from the parent Agent's enabled MCP client set. Unavailable entries are silently omitted rather than blocking the run.
_Avoid_: cross-agent dependency lookup, failed dependency resolution, all-or-nothing dependency loading, inherited workspace Skills

**Declared MCP Client Capability**:
One MCP client named by a present `mcps` field in a **Skill-owned Definition Package**, whose complete exposed tool surface is eligible for the SubAgent Run. The launch snapshot captures the parent Agent's configured client settings; the SubAgent Worker connects it independently and silently omits it when connection fails. Every MCP tool call remains subject to the parent Agent's active Tool Guard, approval, and tenant configuration; a Definition cannot bypass them.
_Avoid_: parent-client reuse, unguarded MCP access, Definition-owned approval bypass, MCP tool allowlist

**Inherited Built-in Tool Set**:
The parent Agent's currently enabled built-in tools, used as the default candidate set for every SubAgent. A Skill-owned SubAgent may narrow that set through TOML `[tools].allow` and `[tools].deny`; a Run-scoped SubAgent inherits it without a Definition-level tool override. The effective set remains bounded by SubAgent policy and Tool Guard/approval controls.
_Avoid_: unrestricted child tools, Tool Guard bypass, inherited Skill Toolkit tools

**Inherited MCP Client Set**:
The parent Agent's enabled MCP client set used by a Run-scoped SubAgent and by a Skill-owned SubAgent whose Definition Package omits `mcps`. A present `mcps` field replaces this default with its named subset; `mcps = []` explicitly disables all MCPs. An MCP client always connects from the immutable launch snapshot.
_Avoid_: live parent-client reuse, inherited workspace Skills, mutable MCP configuration

**Background SubAgent Approval Outcome**:
The result when a Background SubAgent tool call requires human approval: the Tool Guard rejects the call and returns that rejection to the worker. A Background SubAgent Run neither starts an interactive approval request nor waits for a later human decision; only already preapproved or automatically allowed operations execute.
_Avoid_: background approval dialog, paused-for-approval worker, approval bypass

**Agent-owned Definition Selection**:
The Main Agent's explicit selection of an enabled **Agent-owned Stored SubAgent Definition** from the directory exposed by `start_subagent`. It chooses by the Definition's description and trigger keywords, then calls the exact unqualified name; the runtime does not automatically route to it.
_Avoid_: automatic matching, description short-circuit, implicit expert launch

**Skill-owned Definition Selection**:
The Main Agent's choice of a **Skill-owned Stored SubAgent Definition** by comparing the Definition's `description` and declared trigger keywords with the delegated need, then starting it by exact `name`. It does not accept caller-supplied role instructions.
_Avoid_: task-type labels, caller-authored subagent instruction, automatic delegation

**Explicit SubAgent Intent Gate**:
The requirement that the current user message explicitly mentions a SubAgent before the Main Agent receives Background SubAgent tools. Available **Skill-owned Stored SubAgent Definitions** do not independently expose delegation tools or cause automatic delegation.
_Avoid_: definition-driven tool exposure, implicit background work, autonomous delegation

**Main-Agent-only Delegation**:
The rule that Background SubAgent tools are never registered for a SubAgent, including a Skill-owned SubAgent with loaded Skills, MCPs, or mutable built-in tools. Only the Main Agent may create a further SubAgent Run.
_Avoid_: nested delegation, recursive worker tree, SubAgent orchestration

**Skill-owned Definition Trigger Keywords**:
The explicit `trigger_keywords` in a **Skill-owned Definition Package** that help the Main Agent select its Definition for a delegated need. They supplement its `description`; they are not a separate automatic execution mechanism.
_Avoid_: task-type labels, implicit NLP classification, automatic delegation

**Skill-owned Model Reference**:
The optional `[model]` provider-and-identifier pair in a **Skill-owned Definition Package**. It may select only a model already configured for the tenant and available to the Main Agent; when unavailable, the SubAgent silently inherits the Main Agent model and the package cannot contain provider connection or credential settings.
_Avoid_: model-id-only reference, provider configuration, API key, arbitrary model endpoint, failed run for unavailable model

**Skill-owned Model Selection**:
The use of a resolved **Skill-owned Model Reference** by a Skill-owned SubAgent Worker. Any cloud or local model is eligible when the current tenant configuration resolves its provider-and-identifier pair; built-in and ordinary Stored SubAgent Definitions always inherit the parent model.
_Avoid_: cloud-only model selection, model switching for built-in definitions, model switching for ordinary stored definitions, model routing in a run-scoped definition

**Skill-owned Delegation Prompt**:
The layered SubAgent prompt constructed from its Definition `instruction`, fixed runtime safety rules, the delegated `objective`, and optional `background`. The Definition instruction and safety rules are trusted system instructions; `background` is delimited as untrusted task material in that system message, while `objective` is structured user input. Neither task field can replace the Definition's role instruction.
_Avoid_: instruction argument, parent transcript, inherited main-agent prompt

**Skill-qualified SubAgent Name**:
The registry-visible name formed by the runtime as `<skill-name>:<local-name>` for a Definition declared in a **Skill-owned Definition Package**. The Main Agent selects and calls this qualified name; the TOML author supplies only the local name.
_Avoid_: globally unique local name, implicit alternative identifier, display nickname

**Invalid Skill-owned Definition Package**:
An `agents/<agent-name>.toml` file that cannot be parsed or validated as a safe **Skill-owned Stored SubAgent Definition**. It is omitted while its owning Skill and sibling Definition Packages remain available, and it does not alter the Skill package's ordinary security scan.
_Avoid_: whole-skill load failure, unsafe best-effort definition, skipped package scan

**Invalid Agent-owned Definition Package**:
An `agents/<definition-id>.toml` file in an Agent Profile workspace that cannot be parsed or validated as a safe **Agent-owned Stored SubAgent Definition**. The Main Agent omits it without affecting other Definitions, while the expert configuration center reports the validation error for repair; it is distinct from a valid disabled Definition.
_Avoid_: disabled Definition, whole-agent load failure, implicit repair

**SubAgent Definition Store**:
The Agent-Profile-scoped catalog of **Agent-owned Stored SubAgent Definitions**, represented by their **Agent-owned Definition Packages**. It is separate from fixed built-in Definitions and from Skill-owned Definition Packages.
_Avoid_: tenant-global registry, definition-store JSON record, built-in catalog

**Definition Resolution Precedence**:
The name-reservation rule for loaded Definitions: a Skill-qualified SubAgent Name is exclusively owned by its Skill, and an inner local name is isolated by that qualification. An Agent-owned Definition cannot use a built-in name, so exact selection has one owner rather than a runtime precedence tie-breaker.
_Avoid_: name-collision priority, Agent-owned-over-skill resolution, custom builtin override, nondeterministic collision handling

**SubAgent Start Request**:
The compact Main Agent tool request for starting one **SubAgent Run**. It always includes a **SubAgent Name** and objective; its optional **Instruction** is considered only when no loaded Definition resolves by exact name, in which case it creates a **Run-scoped SubAgent Definition**. A resolved built-in, Agent-owned, or Skill-owned Definition ignores caller-supplied Instruction and uses its own.
_Avoid_: required instruction for every start, instruction override, registration payload, full definition schema

**SubAgent Definition Resolution**:
The exact-name decision to use a loaded built-in, Agent-owned, or Skill-owned Definition instead of the **Run-scoped SubAgent Definition** described by a **SubAgent Start Request**. A Definition's own instruction controls execution.
_Avoid_: instruction override, automatic matching, silent definition rewrite

**Definition Match Metadata**:
The audit data written to a **SubAgent Run** and returned by start/status tools to show which **SubAgent Definition Resolution** supplied the worker.
_Avoid_: hidden routing decision, implicit reuse

**Unknown SubAgent**:
An error condition for catalog-facing operations that require an existing reusable Definition by name. It is not part of the compact **SubAgent Start Request**, which falls back to a **Run-scoped SubAgent Definition** when no exact-name resolution occurs.
_Avoid_: start_subagent fallback failure, missing temporary worker

**Instruction**:
The role and operating instructions for a **SubAgent Definition**. It is the canonical SubAgent term across Definition Packages and runtime records, because it describes the delegated worker contract rather than a raw model-message implementation detail.
_Avoid_: system_prompt, prompt text, hidden prompt, prompt.system

**Instruction Size Limit**:
An **Instruction** must be present and non-empty after trimming. Compact start requests reject instructions larger than 8 KB so the worker contract does not become a substitute for delegated task background or source material.
_Avoid_: unlimited system prompt, embedded document payload

**SubAgent Name**:
The stable identifier field named `name`, used by the Main Agent or another runtime entry point to identify a **SubAgent Definition**. It is not the display label shown to users.
_Avoid_: agent_name, display name, nickname, frontend title

**SubAgent Nickname**:
The user-facing display label for a **SubAgent Run** or **Stored SubAgent Definition**. It may be configured by a registration request or assigned from a built-in nickname pool; compact **SubAgent Start Requests** do not accept nickname input, but their run responses may still include an assigned nickname for display.
_Avoid_: agent_name, registry key, stable identifier

**SubAgent Run**:
A single observable execution instance created when the main agent delegates work to a SubAgent Definition. A **SubAgent Run** is not a new SubAgent Definition.
_Avoid_: create subagent, custom subagent, subagent profile

**Delegation Run**:
Alias for **SubAgent Run** when emphasizing the parent-to-worker handoff rather than the worker identity.
_Avoid_: subagent creation

**Background SubAgent Run**:
A **SubAgent Run** that is started by the Main Agent and observed later through status, result retrieval, or cancellation. It is still one run of a **SubAgent Definition**, not a new definition.
_Avoid_: detached subagent, subprocess subagent

**SubAgent Launch Snapshot**:
The immutable execution input captured when a **Background SubAgent Run** starts: its resolved Definition, Effective SubAgent Dependency Set, effective MCP configurations, and selected model or inherited fallback. A running worker does not observe later Skill lifecycle, package, MCP, or model changes.
_Avoid_: live dependency lookup, mid-run skill reload, mutable worker configuration

**SubAgent Launch Diagnostics**:
The audit details of a **SubAgent Launch Snapshot**, including the resolved model and loaded or silently skipped Skill and MCP dependencies. They are visible only through detailed run inspection, while ordinary start, wait, and result projections remain compact.
_Avoid_: default parent-context diagnostics, hidden execution provenance, verbose start result

**SubAgent Research Phase**:
The portion of a **SubAgent Run** in which the worker gathers task evidence and may use its effective read-only tools. It ends before the worker produces its terminal **AgentResult**.
_Avoid_: final response, structured-output phase, unbounded agent loop

**SubAgent Research Completion**:
The normal end of a **SubAgent Research Phase**, reached when the worker replies without requesting a tool. Its evidence becomes a **Bounded SubAgent Research Record** for **SubAgent Text Finalization**; reaching the turn limit instead follows the distinct **SubAgent Turn-limit Finalization** path.
_Avoid_: implicit final tool call, budget-exhaustion normal completion, forced completion

**SubAgent Research Synthesis**:
The concise natural-language, tool-free reply emitted at **SubAgent Research Completion**. It is retained as evidence in the **Bounded SubAgent Research Record** and is not an **AgentResult**.
_Avoid_: terminal result, user-facing completion claim

**Bounded SubAgent Research Record**:
The size-limited record of SubAgent research messages, including assistant replies, tool calls, and tool results. It prioritizes the newest evidence; an oversized message is truncated to fit the remaining capacity and marked as truncated. It is the research evidence supplied to **SubAgent Text Finalization** after normal completion or a turn-limit exit.
_Avoid_: full parent conversation, unbounded transcript, raw worker memory

**SubAgent Research Turn Budget**:
The maximum number of ReAct reasoning turns available to a **SubAgent Research Phase**. It does not include the one terminal **SubAgent Text Finalization** call; both phases share the run's total time budget.
_Avoid_: total model-call budget, finalization turn limit, per-phase timeout

**Skill-owned SubAgent Budget**:
The optional `[budget]` limits in a **Skill-owned Definition Package** for research turns, tool calls, and elapsed time. Omitted values use the platform defaults; supplied values may only stay within the platform maximums and are intersected with the delegated run budget.
_Avoid_: unlimited skill budget, definition-raised platform ceiling, separate finalization budget

**SubAgent Research Phase Controller**:
The SubAgent-specific agent operation that runs the ReAct research loop and reports whether it ended normally or reached its turn limit. It prevents a turn-limit fallback summary from being mistaken for **SubAgent Research Completion**.
_Avoid_: opaque reply outcome, automatic ReAct summarization, runtime-owned protected loop

**SubAgent Turn Usage**:
The actual number of model calls made by a **SubAgent Run**. It includes each research reasoning turn and the one **SubAgent Finalization Attempt**, when one occurs; it can therefore exceed the **SubAgent Research Turn Budget** by one.
_Avoid_: research-only call count, hidden terminal-call cost, turn-budget alias

**SubAgent Text Finalization**:
The terminal, tool-free step after a **SubAgent Research Phase** that asks the model for one final summary text using the supplied research context. The runtime stores that text as the `summary` of the **SubAgent Application Result**; finalization does not gather new evidence or execute work tools.
_Avoid_: ordinary ReAct turn, tool-call loop, structured output

**SubAgent Final Summary**:
The final plain-text summary generated by **SubAgent Text Finalization**. It is the only model-authored content field in a **SubAgent Application Result**.
_Avoid_: structured payload, model-generated result envelope

**SubAgent Finalization Context**:
The bounded handoff supplied to **SubAgent Text Finalization**: the original **DelegationSpec** and a **Bounded SubAgent Research Record**. It excludes the Main Agent conversation and all worker state outside that record.
_Avoid_: full parent conversation, unbounded transcript, implicit memory access

**SubAgent Turn-limit Finalization**:
The one terminal **SubAgent Text Finalization** call made after a **SubAgent Research Phase** reaches its turn budget. It uses the same **SubAgent Finalization Context** as normal completion, but the resulting **SubAgent Application Result** remains partial.
_Avoid_: unbounded transcript replay, extra research turn, skipped terminal response

**SubAgent Turn-limit Partial Result**:
The **SubAgent Application Result** emitted when a **SubAgent Turn-limit Finalization** produces a final summary. It retains that summary while reporting `partial` and `research_turn_limit_reached`, because the research phase did not complete normally.
_Avoid_: completed after turn exhaustion, discarded research summary, runtime failure

**SubAgent Finalization Attempt**:
The single **SubAgent Text Finalization** call allowed after **SubAgent Research Completion** or through **SubAgent Turn-limit Finalization**. A failed attempt produces a **SubAgent Partial Result** and is not retried.
_Avoid_: repeated terminal calls

**SubAgent Application Result**:
The application-constructed terminal result of a **SubAgent Run**. It combines a **SubAgent Final Summary**, when available, with runtime-owned identity, lifecycle status, metrics, and errors.
_Avoid_: model-authored result envelope, raw model response, unvalidated payload

**SubAgent Result Projection**:
The stable, flat caller-facing representation of a **SubAgent Application Result** returned by the Background SubAgent tools. It exposes the terminal summary without exposing the full persisted run record.
_Avoid_: payload-only API, nested response migration, internal schema leak

**SubAgent Partial Result**:
An **AgentResult** that retains an available final summary without representing the delegated task as completed. It is produced when **SubAgent Text Finalization** fails, or when **SubAgent Turn-limit Finalization** produces a summary after research exhausted its budget.
_Avoid_: completed result with warning, discarded research, research timeout result

**Background SubAgent Concurrency Limit**:
The maximum number of **Background SubAgent Runs** that one runtime scope may have running at the same time. When the limit is reached, a new background start request is rejected as blocked rather than queued.
_Avoid_: queue size, worker pool size, soft recommendation

**Background SubAgent Run Status**:
The lifecycle state of a **Background SubAgent Run** as observed by the Main Agent: `pending`, `running`, `paused`, `completed`, `partial`, `failed`, `cancelled`, or `expired`. `partial` retains usable research evidence when terminal validation cannot complete. It is separate from the `status` field inside an **AgentResult**, which describes the delegated task outcome. `expired` is reserved for future supervisor cleanup semantics and is not emitted by the first background-tool implementation.
_Avoid_: AgentResult status, tool call status, process exit code

**Background SubAgent Tools**:
The Main Agent tools for managing **Background SubAgent Runs**: `start_subagent`, `wait_subagent`, `get_subagent`, and `cancel_subagent`. They are the intended SubAgent tool surface for the next implementation stage.
_Avoid_: agent tools, generic worker tools, synchronous delegate tool

**wait_subagent Tool**:
A Main Agent tool that performs a bounded wait and returns basic run identity, status information, and terminal run results for the current tenant-and-agent scope's observable **Background SubAgent Runs**. It is not a diagnostic, routing-audit, worker-inspection, or historical run-browsing surface.
_Avoid_: list agents, background queue browser, automatic completion callback, debug inspector, routing audit

**SubAgent Run Cancellation**:
The act of cancelling the execution handle that owns a **Background SubAgent Run** and marking that run as cancelled. It does not imply recursively terminating tool-owned subprocesses unless a later execution backend explicitly supports that behavior.
_Avoid_: kill process tree, hard stop all tools

**SubAgent Run Monitor**:
A user-facing view that shows the **Background SubAgent Runs** associated with the current Main Agent conversation. It is scoped to the current conversation and is not an agent-wide operations console.
_Avoid_: global subagent dashboard, worker pool monitor, all-agent status panel

**助手**:
The chat-facing display term for one **Background SubAgent Run**. It deliberately hides the internal implementation term “SubAgent” from users without changing the run's identity, API contract, or runtime semantics.
_Avoid_: 用于 API 字段、事件名或运行时领域模型的 Assistant/SubAgent 替换

**SubAgent Run Snapshot**:
A point-in-time observable summary of the current conversation's **Background SubAgent Runs**. It is the authoritative state used by user-facing monitoring surfaces, while live stream events may only prompt refresh.
_Avoid_: stream-only state, frontend cache, tool result transcript

**SubAgent Budget Consumption**:
The observable consumption of a **Background SubAgent Run**'s time and turn budgets, shown as used against total for each dimension. It is not a task-completion percentage; the live turn value is a persisted runtime observation and the terminal value is the final **SubAgent Turn Usage**.
_Avoid_: task progress, completion percent, model confidence, estimated turn count

**Frontend SubAgent Stop Request**:
A user action from a **SubAgent Run Monitor** that asks the runtime to cancel one specific **Background SubAgent Run** directly. It is not a natural-language instruction for the Main Agent to decide whether to call a tool.
_Avoid_: chat stop message, assistant-mediated cancellation, generic task stop

**SubAgent Run Stop Eligibility**:
The rule that only an actively running **Background SubAgent Run** can expose a user stop action in the **SubAgent Run Monitor**. Terminal, pending, paused, expired, and already-cancelled runs remain visible as status records but are not clickable stop targets.
_Avoid_: remove record action, terminal cleanup button, clickable status row

**SubAgent Stop Pending State**:
The temporary user-facing state shown after a **Frontend SubAgent Stop Request** has been submitted and before the next **SubAgent Run Snapshot** confirms the run's terminal status. It disables repeated stop actions without implying the run has already been cancelled.
_Avoid_: confirmed cancellation, terminal stopped state, retry button state

**SubAgent Execution Backend**:
The runtime mechanism used to execute a **SubAgent Run**, such as an in-process task or a separate operating-system process. It is an implementation boundary and does not change the meaning of **SubAgent Run**.
_Avoid_: subagent type, agent definition source

**Main Agent**:
The user-facing agent that owns global task understanding, user interaction, mode decisions, and final responses.
_Avoid_: parent bot, orchestrator bot

**Chat Checkpoint**:
A Chat-scoped recoverable state container that identifies the current task and retains a compact index of earlier completed tasks in the same Chat. Starting an explicit new task replaces its current task; `/new` resets the Chat Checkpoint.
_Avoid_: global task state, session summary, cross-chat checkpoint

**Checkpoint Record**:
The versioned, structured source of truth for a Chat Checkpoint. A Checkpoint Record distinguishes confirmed state from unresolved work and retains references to its supporting evidence.
_Avoid_: free-form summary, model-only memory, untraceable state

**Evidence Recovery**:
The on-demand, Chat-scoped restoration of an original conversation or tool-result fragment identified by a Checkpoint Record. Exact evidence references take precedence; a bounded current-epoch lookup may otherwise narrow by text, kind, and time interval. It adds only the evidence needed for the Current Task and does not replace the checkpoint state.
_Avoid_: cross-chat history search, automatic full-history injection, summary reconstruction

**Checkpoint Update**:
The validated replacement of a Checkpoint Record from deterministic conversation facts and semantic task-state interpretation. It cannot discard evidence before the replacement record has passed validation.
_Avoid_: markdown-only rewrite, unvalidated summarization, destructive compaction

**Compaction Transaction**:
The per-Chat operation that validates and durably installs a Checkpoint Update together with its archived source history. It either exposes a recoverable checkpoint or retains enough pending state to finish safely after recovery.
_Avoid_: overwrite-in-place compaction, archive-without-state, lost concurrent event

**Checkpoint Event Journal**:
The ordered, append-only Chat-scoped record of deterministic events that occurred after the event sequence incorporated by the active Checkpoint Record. It preserves the current-state delta until a later Checkpoint Update incorporates it.
_Avoid_: second free-form summary, mutable progress list, discarded pre-compaction event

**Recent Event Delta**:
The budget-bounded model-context projection of unincorporated entries from the Checkpoint Event Journal. It supplies current deterministic facts without duplicating the original interaction or becoming another semantic summary.
_Avoid_: all event history, raw tool output duplication, per-turn resummarization

**Context Budget Stage**:
One of the ordered context-capacity states—Lightweight Governance, Active Compaction, or Emergency Degradation—that determines how a Chat Checkpoint and its online history are reduced before a model call.
_Avoid_: single hard truncation threshold, post-overflow-only compaction

**Proactive Incremental Compaction**:
The asynchronous, non-blocking preparation and validation of a bounded Chat Checkpoint update before an Active Compaction threshold is reached. Its prepared candidate is installed only when its snapshot remains valid at an Active Compaction or Emergency Degradation threshold.
_Avoid_: threshold-only bulk compaction, blocking reply-path compression, per-message full resummarization

**Precompaction Candidate**:
A validated but inactive Checkpoint Update derived from a stable Chat snapshot and its exact source-message prefix. It may be installed without another ReMe call only when its base record revision, event sequence, and source prefix remain valid.
_Avoid_: stale summary cache, immediately active checkpoint, overwrite of newer events

**Elastic Context Budget**:
The allocatable capacity remaining after permanent context and model-output safety space are protected. Checkpoint projection, recent original interaction, and recovered evidence compete within it according to the Current Task rather than occupying fixed partitions.
_Avoid_: fixed percentage partition, unused reserved context, unbounded recovery injection

**Context Epoch**:
The portion of a Chat's context history eligible for default model-context assembly after a `/new` or `/clear` boundary. Earlier epochs remain durable Chat evidence but require explicit user intent before they may be recovered.
_Avoid_: automatic pre-reset recovery, physical deletion on context reset, cross-epoch default context

**Task Transition**:
The explicit change of the Current Task within a Chat Checkpoint. It occurs only when the user introduces an independent goal after completion, explicitly starts a new task, or resets the Chat; corrective and incremental requests remain part of the Current Task.
_Avoid_: every user turn is a new task, inferred task split, destructive history reset

**Agent Profile**:
A tenant-owned runtime configuration and workspace identity for one runnable Agent. An **Agent Profile** is distinct from a **SubAgent Definition**, which is a versioned delegation worker description.
_Avoid_: agent-level config, subagent profile, worker profile

**Default Agent Profile**:
The tenant's built-in **Agent Profile** with the stable identifier `default`. It is the sole scope of the first Agent Profile Hook console release and remains available rather than being disabled or removed.
_Avoid_: selected agent, active-agent selector

**Default Agent Profile Hook Access**:
The ordinary tenant-scoped access boundary for changing Default Agent Profile Hooks and their scripts. The first release adds no separate manager or administrator role requirement.
_Avoid_: manager-only hook access, global hook administrator

**Default Agent Profile Hook Audit Record**:
A best-effort structured application-log event for a Default Agent Profile Hook or Hook Script change. It identifies the actor, time, action, affected script and digest when applicable, and a configuration-delta summary without retaining script content or runtime hook payloads; a logging failure does not prevent the action.
_Avoid_: audit database table, hook execution log, full script archive, hook payload audit

**Agent Profile Hook**:
A lifecycle-hook configuration owned by exactly one **Agent Profile**. It applies only while that Agent Profile runs, rather than across a tenant or through a reusable Skill.
_Avoid_: agent-level hook, tenant hook, skill hook

**Agent Profile Hook Distribution**:
The explicit one-time copying of a source tenant's complete executable **Agent Profile Hook** unit to selected target tenants' Default Agent Profiles. The unit contains the Hook configuration and every referenced **Agent Profile Hook Script**; each target receives its own independent copy.
_Avoid_: shared Hook, configuration-only distribution, cross-tenant Hook ownership

**Agent Profile Hook Distribution Merge**:
The target-specific application of an **Agent Profile Hook Distribution**, where a source Matcher Group replaces a target Matcher Group with the same **Agent Profile Hook Matcher Group Identifier**, including its matcher and ordered Handlers. Source-only Matcher Groups are added and target-only Matcher Groups remain unchanged.
_Avoid_: Handler-ID merge, full configuration replacement, implicit group matching

**Agent Profile Hook Distribution Transaction**:
The independent all-or-nothing application of one **Agent Profile Hook Distribution** to one target tenant. Its referenced scripts, configuration merge, and activation either all complete or leave that target unchanged; outcomes for other target tenants remain independent.
_Avoid_: cross-tenant transaction, partial target update, configuration-only success

**Agent Profile Hook Distribution Selection**:
One or more source **Agent Profile Hook Matcher Groups** explicitly selected for an **Agent Profile Hook Distribution**. Each selected Matcher Group and its referenced scripts form the distribution payload.
_Avoid_: single-Handler distribution, implicit full-profile distribution, event-name selection

**Agent Profile Hook Distribution Source Snapshot**:
The saved configuration revision and controlled script artifacts from which an **Agent Profile Hook Distribution** is made. An unsaved Hook configuration draft cannot be a distribution source.
_Avoid_: draft distribution, live mutable source, inferred source revision

**Agent Profile Hook Distribution Confirmation Freshness**:
The rule that confirming an **Agent Profile Hook Distribution** does not require its source revision or script digests to match the values observed when the distribution dialog opened. The distribution uses the latest saved source configuration and script artifacts available when it executes.
_Avoid_: confirmation snapshot lock, stale-source conflict, draft source

**Missing Agent Profile Hook Distribution Selection**:
A source validation failure where a Matcher Group selected for an **Agent Profile Hook Distribution** no longer exists when the request executes. It rejects the entire distribution before any target tenant is changed.
_Avoid_: silently skipped group, per-target missing-group result, partial source payload

**Agent Profile Hook Distribution Audit Record**:
A best-effort structured application-log record for one attempt to apply an **Agent Profile Hook Distribution** to one target tenant. It identifies the actor, source and target tenants, source revision, selected Matcher Groups, script digests and transfer outcomes without retaining script content or Hook runtime payloads.
_Avoid_: batch-only audit record, script-content archive, Hook execution log

**Agent Profile Hook Distribution Access**:
The source-scoped authorization boundary for initiating an **Agent Profile Hook Distribution**. An authorized caller may target only tenants in its current source scope, and may not target its own current tenant.
_Avoid_: cross-source distribution, self-distribution, manager-only Hook distribution

**Agent Profile Hook Distribution Target Bootstrap**:
The initialization of a manually specified target tenant's Default Agent Profile in the current source scope before applying an **Agent Profile Hook Distribution**. The per-target result identifies whether this Bootstrap occurred during the distribution.
_Avoid_: discovered-target-only distribution, uninitialized target write, cross-source bootstrap

**Agent Profile Hook Distribution Credential Boundary**:
The rule that an **Agent Profile Hook Distribution** never reads or copies values from a tenant runtime environment or secret store. It copies selected Hook configuration verbatim, including literal command environment and HTTP header values, while each target resolves configuration references against its own runtime values.
_Avoid_: runtime-secret distribution, shared tenant credential, target-secret preflight

**Agent Profile Hook Distribution Script Conflict**:
A target-specific conflict where a selected source script has the same name but different content from a script referenced by a target Matcher Group retained outside the distribution. The target distribution fails unless the scripts have the same digest or every target reference belongs to a Matcher Group replaced by the distribution.
_Avoid_: silent script replacement, automatic script renaming, retained-group mutation

**Agent Profile Hook Distribution Script Transfer**:
The copying of selected source **Agent Profile Hook Scripts** into a target's controlled script library as part of an **Agent Profile Hook Distribution**. It preserves the source script artifact without running a target-side script safety scan.
_Avoid_: target-side scan, unverified arbitrary-file copy, script upload

**Agent Profile Hook Handler**:
One configured action within an **Agent Profile Hook**. It is either a command handler, an HTTP handler, or a prompt handler; only a command handler may reference one or more **Agent Profile Hook Scripts**.
_Avoid_: shell hook, script hook configuration

**Agent Profile Hook Script**:
A Python or shell executable asset owned by one **Agent Profile** and referenced through a command handler's ordered arguments. One command handler may reference multiple Agent Profile Hook Scripts; scripts cannot be deleted, but a same-name upload replaces the stored content after an explicit warning.
_Avoid_: shared hook script, skill hook script, arbitrary binary, disposable script

**Agent Profile Hook Script Replacement**:
The explicit same-name upload that replaces an Agent Profile Hook Script's content for later Hook events. It records both the prior and replacement script digests and does not interrupt an executing Hook.
_Avoid_: silent overwrite, script deletion

**Agent Profile Hook Script Path Boundary**:
The rule that a command handler may reference executable programs and ordinary arguments freely, but every argument used as a script must resolve to an Agent Profile Hook Script owned by the Default Agent Profile. Paths outside that controlled script set are not script references.
_Avoid_: workspace script reference, absolute script path, path escape

**Agent Profile Hook Script Type Boundary**:
The first-release upload policy accepts only Python and shell source files with `.py`, `.sh`, `.bash`, or `.zsh` names. It excludes extensionless files and binary assets.
_Avoid_: extensionless script, binary hook asset

**Agent Profile Hook Script Safety Scan**:
The application security scan applied to every Agent Profile Hook Script upload or replacement. It follows the active scan policy: disabled, warning-only, or blocking for unsafe findings.
_Avoid_: unconditional script rejection, unscanned replacement

**Agent Profile Hook Script Upload Batch**:
One or more Hook Script files submitted together to the script library. Each file is validated and scanned independently, so successful files are retained while failed files report their own reasons.
_Avoid_: all-or-nothing script upload, silent partial upload

**Agent Profile Hook Script Upload Limit**:
The first-release storage boundary of at most 1 MB per Hook Script and at most 20 files per Upload Batch.
_Avoid_: unrestricted script upload, general file storage

**Agent Profile Hook Activation Boundary**:
The point after a saved Agent Profile Hook configuration has reloaded, from which later Hook events use it. A Hook already executing continues with its prior configuration and scripts.
_Avoid_: immediate interruption, retroactive Hook update

**Agent Profile Hook Configuration Removal**:
The saved removal of a Handler or Matcher Group from the Default Agent Profile Hook configuration. It stops later Hook events from resolving that configuration while leaving its Hook Scripts retained in the script library.
_Avoid_: script deletion, immediate Hook interruption

**Agent Profile Hook Configuration Revision**:
The version token for the complete Default Agent Profile Hook configuration. A save must name the revision it was based on; a mismatched current revision is a conflict rather than a silent overwrite.
_Avoid_: last-writer-wins configuration save, invisible concurrent overwrite

**Agent Profile Hook Manual Test**:
An explicitly confirmed execution of one draft Agent Profile Hook Handler with an editable sample context. It does not save configuration, activate a reload, or consume once-only state; it performs the handler's real external effects, and its result is audited and presented in a redacted, bounded form.
_Avoid_: full Hook replay, production event replay, unsandboxed preview

**Agent Profile Hook Console**:
The Default Agent Profile's user interface for maintaining its Hooks, Handlers, Scripts, and manual tests. It is a dedicated Run Center page with configuration and script-library areas; its changes emit audit logs, which are viewed through the application log system rather than the console.
_Avoid_: raw configuration editor, partial Hook form

**Agent Profile Hook Handler Identifier**:
The stable identifier of one Agent Profile Hook Handler. It is generated by the console by default, may be edited, and must be unique across the Default Agent Profile Hook configuration.
_Avoid_: duplicate handler ID, display-only handler name

**Agent Profile Hook Matcher Group Identifier**:
The stable identifier of one Agent Profile Hook Matcher Group. It is generated by the console by default, may be edited, and must be unique across the Default Agent Profile Hook configuration.
_Avoid_: duplicate group ID, event-local-only group ID

**Plan Mode**:
A user-visible planning state where the Main Agent itself runs under reduced planning permissions and interacts with the user through planning cards before execution continues.
_Avoid_: dry run, planning prompt

**Proposed Plan**:
A planning artifact presented by the Main Agent for user review before continuing work. A Proposed Plan contains a plan id, title, summary, steps, risks, and verification items.
_Avoid_: permission request, execution unlock

**Plan Review Decision**:
The user's response to a Proposed Plan: `revise`, `execute`, or `exit_plan`. `revise` enters or keeps Plan Mode active for replanning, `execute` accepts the persisted Proposed Plan and continues in normal mode, and `exit_plan` closes Plan Mode without starting a Main Agent execution run by default.
_Avoid_: tool approval, permission grant

**Plan Interaction Card**:
A structured chat UI card used by the Main Agent to ask for planning clarification or present a Proposed Plan. A Plan Interaction Card is user-facing and is not emitted directly by a SubAgent.
_Avoid_: subagent question card, free-form prompt hack

**Plan Interaction Composer Replacement**:
A blocking chat composer state where one active Plan Interaction Card replaces the normal user input panel until the user completes or dismisses that card. It owns the visible input controls for that moment; the normal composer input, send action, attachments, quick menu, and Plan Mode prefix controls are not concurrently available.
_Avoid_: card above composer, floating plan card, parallel input form

**Active Plan Interaction Card**:
The latest non-superseded Plan Interaction Card in the chat timeline that is currently waiting for user action. At most one Active Plan Interaction Card owns the Plan Interaction Composer Replacement at a time.
_Avoid_: all pending cards, card type priority, parallel active cards

**Planning Clarification Card**:
A Plan Interaction Card that asks the user for missing planning information using single choice, multiple choice, or text input.
_Avoid_: generic form, survey

**Custom Clarification Response**:
A user-authored text answer shown as an always-visible input on a top-level single-choice or multiple-choice Planning Clarification Card. For single choice it is mutually exclusive with selecting a listed option; for multiple choice it may be submitted together with listed options. It is not a field-level option inside a structured clarification form.
_Avoid_: collapsed other option, form field other option, generated option, hidden option id

**Plan Interaction Response**:
The user's structured answer to a Plan Interaction Card, submitted as the next normal chat turn with metadata that identifies the card and selected or entered value.
_Avoid_: hidden plan API update, out-of-band form submission

**Plan Interaction Event**:
A persisted chat-context event that records a user's submitted action on a Plan Interaction Card, such as answering a clarification or deciding on a Proposed Plan. It is metadata, not user-visible prose, and it identifies the card by stable source identity first with runtime instance identity only as a fallback.
_Avoid_: browser cache flag, local UI state, hidden text command

**Plan Review Submission**:
A Plan Interaction Event that records the user's `revise`, `execute`, or `exit_plan` decision for a Proposed Plan. Restored Plan Review Cards use this event and any backend-submitted status as the sources of truth for whether the review has already been handled.
_Avoid_: browser-submitted flag, frontend-only review state

**Plan Revision Input**:
The next user-authored chat turn after the user chooses to continue modifying a Proposed Plan. It is the content submitted with a `revise` Plan Review Decision and keeps Plan Mode active.
_Avoid_: empty revise click, implicit plan rejection

**Plan Mode Exit Feedback**:
The user-visible confirmation that an `exit_plan` Plan Review Decision succeeded. It is expressed by the Plan Mode control leaving the composer area, not by adding a chat message or starting a Main Agent run.
_Avoid_: assistant exit message, plan execution result

**Plan Review Snapshot**:
A read-only historical presentation of a Proposed Plan after it has appeared in the chat history. A **Plan Review Snapshot** preserves review context but is not the active place for submitting a Plan Review Decision.
_Avoid_: stale actionable card, replayed plan approval

**Accepted Plan Review Snapshot**:
A Plan Review Snapshot for a Proposed Plan whose `execute` Plan Review Decision has been submitted. It shows that the plan was accepted and normal Main Agent execution has started or will start.
_Avoid_: active execution approval, editable accepted plan

**Revised Plan Review Snapshot**:
A Plan Review Snapshot for a Proposed Plan whose `revise` Plan Review Decision has been submitted. It shows that the previous proposal was sent back for modification and may include the user's Plan Revision Input as review context.
_Avoid_: active revision form, rejected plan

**Planning Clarification Dismissal**:
The user's decision to close the current Planning Clarification Card without submitting a Plan Interaction Response. It is a current-runtime UI action, leaves Plan Mode active, and restores normal chat input for the user; after session restore it is not remembered unless the clarification was superseded by a later user message.
_Avoid_: exit Plan Mode, reject plan, submit empty response

**Planning Clarification Replay**:
The behavior of showing a Planning Clarification Card again after a page reload or session restore. It is not part of the intended user flow for a card that was already displayed once in the current chat.
_Avoid_: history replay, reload restoration, persistent clarification prompt

**Planning Clarification Supersession**:
The point where a Planning Clarification Instance is overtaken by any later user message in the same chat session. A superseded clarification is not shown again when the session is restored, while a later assistant message may still create a new Planning Clarification Instance with the same content.
_Avoid_: render-seen state, frontend cache flag, browser storage marker

**Planning Clarification Instance**:
One visible Planning Clarification Card occurrence tied to a specific assistant message. Two cards with the same内容 but different assistant messages are different instances.
_Avoid_: content fingerprint, semantic duplicate, shared clarification prompt

**Plan Interaction Tool**:
A built-in Main Agent tool that emits Plan Interaction Cards through validated structured metadata.
_Avoid_: markdown JSON card, frontend text parser

**Plan Interaction Tool Availability**:
The source-scoped runtime rule that the Plan Clarification Tool and Proposed Plan Tool are available together in Plan Mode and, outside Plan Mode, only when enabled by that source's Source System Configuration. A configuration change applies to subsequent Agent requests; enabling ordinary-mode availability makes the tools callable without applying Plan Mode's planning instructions or permission restrictions.
_Avoid_: automatic Plan Mode, forced planning workflow, global tenant switch

**Plan Interaction Turn Boundary**:
The conversation boundary created when the Main Agent emits a Plan Interaction Card through a Plan Interaction Tool. The current Main Agent turn finishes the already-started tool-call batch, then ends without another reasoning step and waits for a user Plan Interaction Response, regardless of the current Plan Mode State.
_Avoid_: optional pause, prompt-only guideline, Plan Mode-only stop, sibling tool cancellation

**Plan Clarification Tool**:
The Plan Interaction Tool used by the Main Agent to ask the user a single planning clarification question.
_Avoid_: generic question tool, subagent prompt

**Proposed Plan Tool**:
The Plan Interaction Tool used by the Main Agent to present a Proposed Plan for `revise`, `execute`, or `exit_plan` review.
_Avoid_: final answer tool, permission approval tool

**Structured Interaction Envelope**:
A runtime transport contract that carries validated interactive state and user responses between an agent workflow and a specialized CoPaw interface. Its first product consumer is the W+ SOP Workspace; it does not by itself create a generic interactive-skill product surface. For W+ SOP clarification, a question batch contains one to three typed questions; supported response controls are single-select, multi-select, and free text, including evidence-backed options with an Other text path. A batch is submitted atomically after all required responses are complete. Each submitted batch becomes one auditable owning-Chat response summary carrying the clarification session ID, round number, and revision number, and it triggers exactly one subsequent Miner turn. During generation the UI may stream lifecycle progress, but answer controls appear only after the complete question batch passes envelope validation and then become available atomically.
_Avoid_: Plan Interaction Card, markdown JSON card, generic skill workspace

**W+ SOP Answer Revision**:
An append-only correction to an earlier answer in the current clarification history. Submitting it increments the revision, invalidates every downstream question, answer, and derived result, and regenerates from the corrected point. The owning Chat retains the original messages, appends a revision record containing the old value, new value, revision number, and affected rounds, and visually marks invalidated records; the Miner consumes only the current valid revision. Editing is allowed only while the session is active; a paused session must be resumed first, and completed or terminated sessions are permanently read-only.
_Avoid_: edited Chat message, deleted audit history, branching valid answers

**W+ SOP Workspace**:
The W+-specific CoPaw interface for conducting and reviewing one W+ SOP Clarification Session. It is a specialized view of the owning Chat, not a separate conversation or a generic interface for all skills. It is the sole answer-submission surface while the session is active. The owning Chat renders each current question batch as a read-only audit card with session status and a Return to SOP Workspace action; it must not duplicate active answer controls. Navigating away from the workspace does not pause or otherwise mutate the session: the owning Chat remains locked until the user explicitly saves and exits, completes, or terminates the session.
_Avoid_: Plan Mode, standalone chat, generic skill workspace

**W+ SOP Session Control Card**:
The single mutable Chat card representing one W+ SOP Clarification Session and serving as its stable navigation or recovery entry. Its state changes in place across Active, Pending Exit, Paused, Completed, and Terminated, while question, answer, and revision audit cards remain append-only and immutable. While the session is Active or Paused, the owning Chat also derives a non-message sticky bar above the input area: Return to SOP Workspace when active and Resume SOP when paused. The sticky bar disappears after completion or termination.
_Avoid_: one resume card per transition, latest question as resume state, multiple active controls

**W+ SOP Clarification Session**:
A revisioned clarification process produced by `wplus-sop-miner`, bound to one owning Chat and containing the currently valid questions, answers, confirmed facts, and SOP result state. An owning Chat may have at most one active or paused session at a time. After that session is terminated, a new session may be created in the same Chat while the earlier session and its cards remain available as history. Producing and validating the final SOP does not by itself complete the session: the workspace must then present the Miner's evidence-backed memory candidates for explicit per-candidate consent, with a Skip All action. The session completes normally only after those choices are resolved. Normal completion restores the owning Chat input immediately but leaves the user on the final workspace result view; the Chat card becomes a read-only Completed entry that can reopen the result and history. Pausing restores normal Chat input, but later ordinary Chat turns remain outside the saved SOP state; resuming uses only the session's current valid revision unless the user explicitly adds information from inside the workspace.
_Avoid_: Chat session, skill invocation, Plan Mode session

**Pending W+ SOP Exit**:
A transitional session state created when the user requests Save and Exit or Terminate while the Miner is generating. The workspace stops accepting new answers, allows the in-flight response to finish and persist, and only then applies the requested exit action so frontend and agent state remain consistent.
_Avoid_: immediate stream disconnect, discarded response, disabled exit control

**W+ SOP Recoverable Failure**:
A terminal generation failure recorded against the last stable session revision after reconnecting to the same in-flight Chat run is no longer possible. The workspace preserves that stable state and offers an idempotent Retry Current Turn, Save and Exit, and Terminate; retrying must not append a duplicate answer audit record.
_Avoid_: duplicate turn, automatic new generation, forced pause

**W+ SOP Termination Summary**:
The read-only artifact retained when a user permanently terminates an incomplete clarification session. It lists confirmed facts, explicit unknowns, unresolved questions, completed and incomplete stages, and the termination point, and must state that it is not a valid SOP. It cannot be passed to `wplus-skill-builder`.
_Avoid_: partial SOP, assumed completion, builder-ready result

**W+ SOP Result Bundle**:
The validated final output of a normally completed clarification session: the readable SOP, `sop_spec.json`, and escaped HTML visualization. The first workspace release supports viewing and downloading these artifacts and states that they are ready for a later explicit `wplus-skill-builder` invocation; it neither invokes nor embeds the Builder.
_Avoid_: automatic Builder invocation, incomplete SOP bundle, implicit handoff

**W+ SOP Workspace V1 Privacy Scope**:
The first workspace release adds no dedicated client or server feature for detecting, blocking, or automatically redacting sensitive text in clarification answers. Existing CoPaw controls and the Miner's privacy rules remain applicable, but new workspace-specific sensitive-input enforcement is outside this feature scope.
_Avoid_: claimed PII protection, implicit redaction, weakening Miner policy

**W+ SOP Workspace Entry**:
The explicit transition from an owning Chat into a W+ SOP Workspace. A direct user invocation of `wplus-sop-miner` may enter immediately; an implicitly detected invocation must first render a clickable Chat confirmation card with Confirm and Reject actions. Confirm creates the W+ SOP Clarification Session, uses the already-submitted original request as the Miner's initial input, navigates to the new workspace, and begins producing the first clarification question without requiring resubmission. Reject cancels the Miner invocation, keeps the user in normal Chat, and returns the original request to the normal Chat agent for processing. The rejected turn must suppress `wplus-sop-miner` re-detection so the confirmation card cannot loop, and it does not create or activate a W+ SOP Clarification Session.
_Avoid_: silent route switch, automatic implicit entry, Plan Mode entry

**Plan Delegation**:
An optional Main Agent action in Plan Mode that creates a SubAgent Run through the normal delegation mechanism. Plan Delegation is allowed but is never automatic or required by Plan Mode.
_Avoid_: default plan subagent, automatic plan researcher

**Planning Readonly Policy**:
The reduced permission policy applied to the Main Agent in Plan Mode. It allows repository reading, searching, current-time lookup, readonly shell commands, and readonly SubAgent delegation while forbidding workspace mutation, tests, deployment, migration, and progress/static-copy side effects.
_Avoid_: full readonly mode, approval mode

**Explicit Plan Entry**:
A user-visible action that starts Plan Mode for a turn or session. Plan Mode is not entered silently by Main Agent inference.
_Avoid_: automatic plan detection, implicit planning

**Plan Mode State**:
The chat-session state indicating whether future turns in that chat should run in Plan Mode. One chat session has at most one current Plan Mode State.
_Avoid_: one-shot plan flag, global plan switch

**Scheduled Job**:
A recurring task definition owned by a tenant and executed by the runtime at configured times. One **Scheduled Job** can have many **Scheduled Runs**.
_Avoid_: cron config, timer task

**Scheduled Firing Count**:
The number of planned firing occurrences produced by enabled, active **Scheduled Job** definitions within a selected time range. One Scheduled Job contributes once for every matching cron occurrence. A **Scheduled Firing Count** describes planned schedule density only; it does not prove that runs are queued, delayed, executing, or backlogged.
_Avoid_: backlog count, running task count, execution count

**Scheduled Run**:
A single execution of a **Scheduled Job**, whether triggered by schedule or manually.
_Avoid_: cron call, job instance

**Scheduled Run Intent**:
A queued, claimable work item representing a due **Scheduled Run** before execution starts. Resource-aware dispatch orders **Scheduled Run Intents**; it does not rewrite the owning **Scheduled Job** definition. A **Scheduled Run Intent** may represent the parent broadcast dispatch run or a child run in the same **Dispatch Batch**. A **Scheduled Run Intent** does not create user notification state; notification remains tied to the eventual execution record.
_Avoid_: cron offset, child job priority, job rewrite

**Dispatch Batch**:
The set of **Scheduled Run Intents** for one planned firing of the same parent **Scheduled Job** for the same source. In the first rollout, the batch contains a parent dispatch intent plus its broadcast child intents; the parent intent expands or verifies the child intent set, and child intents then execute in the stable **Batch Dispatch Order**.
_Avoid_: time bucket, queue shard, child job group

**Dispatch Intent Role**:
The role of a **Scheduled Run Intent** inside a **Dispatch Batch**. A parent intent represents the batch dispatch step for the broadcast source job, while child intents represent target scheduled runs that execute existing child **Scheduled Jobs**.
_Avoid_: task type, notification type, model pool

**Dispatch Intent Queue**:
The Scheduler-owned durable queue of **Scheduled Run Intents**. The **Cron Scheduling Service** claims due intents from this queue and calls the SWE internal callback to start the referenced **Scheduled Job**; Scheduler owns ordering, locking, retry visibility, and dispatch telemetry before execution starts. Monitor may persist and display the queue records, but it does not host the dispatch loop. The first rollout scope is broadcast parent and child **Scheduled Run Intents**.
_Avoid_: local SWE queue, external scheduler callback, notification queue

**Cron Scheduling Service**:
An independent Scheduler service hosted outside both the SWE execution runtime and the Monitor observability runtime. It owns due-intent dispatch, callback handoff to SWE, immediate refill after completed scheduled work, periodic worker-capacity adjustment, and dispatch telemetry. It does not execute agent work itself; SWE remains the execution owner, and Monitor remains the observability and persistence surface.
_Avoid_: SWE dispatch worker, external scheduler job, notification worker

**Intent Dispatch Handoff**:
The transition that records a claimed **Scheduled Run Intent** as handed off to SWE through the internal cron callback. Before handoff, stale locks and callback retry backoff belong to the **Dispatch Intent Queue**. After handoff, success, failure, and notification belong to the normal **Scheduled Run** execution record; dispatch-managed completion feedback returns to Scheduler so it can update the intent and immediately make the next dispatch decision.
_Avoid_: execution completion, notification status, run result

**Broadcast Child Trigger Compatibility**:
The first dispatch-queue rollout keeps broadcast child **Scheduled Jobs** and their offset metadata for display, audit, and rollback, but child jobs are not externally scheduled. The parent broadcast dispatch step writes or verifies the child **Scheduled Run Intents** that control real execution order.
_Avoid_: child cron execution, offset-driven dispatch

**Dispatch Capacity Profile**:
A source-level runtime configuration that declares baseline worker capacity for **Scheduled Run Intents**, optionally by recurring local time window and **Dispatch Model Pool**. Its time windows are interpreted in the source's dispatch timezone, not in an individual **Scheduled Job** timezone. It seeds dispatch capacity but does not guarantee that many workers will run when runtime feedback reports pressure.
_Avoid_: fixed cron scatter, hard-coded time node, job concurrency

**Dispatch Model Pool**:
A dispatch-only resource bucket used to group **Scheduled Run Intents** that compete for the same model capacity. Its key is the resolved `provider_id/model` pair from the run's effective model. It does not change **Execution Model Slot** resolution; a run still executes with its resolved provider and model.
_Avoid_: tenant model, active model, model override

**Effective Dispatch Capacity**:
The worker capacity currently allowed by the dispatcher after combining the **Dispatch Capacity Profile** with runtime feedback such as rate limits, timeouts, latency, backlog, and success rate. It follows an additive-increase, multiplicative-decrease rule: pressure lowers capacity quickly, while stable success raises it gradually up to the active profile window's cap.
_Avoid_: configured worker count, static quota

**Worker Capacity Snapshot**:
A monitorable record of a dispatch worker capacity decision for a source and **Dispatch Model Pool**, including configured profile values, effective capacity, feedback signals, and the reason for any increase or decrease.
_Avoid_: log-only worker count, static config

**Dispatch Callback Source**:
The explicit callback-origin marker that distinguishes a SWE internal callback request from the **Cron Scheduling Service** from a legacy external scheduler callback. Batch-managed scheduled work only starts when the source is the scheduling service.
_Avoid_: inferring origin from request shape, jobParam means external, direct body means internal

**Dispatch Telemetry Record**:
A monitorable record written for dispatch-intent lifecycle events such as queued, claimed, callback-dispatched, retry-scheduled, stale-lock recovered, and linked execution completion. It supports child-task execution monitoring without replacing the normal execution record.
_Avoid_: notification record, execution replacement, debug log

**Viewer Heat Score**:
A bounded priority signal for a user or tenant, derived from recent **Scheduled Run** result reads. It combines read rate and read recency over a configured lookback window, and is used only to determine the initial **Batch Dispatch Order** within a batch.
_Avoid_: total read count, user importance, notification priority

**Batch Dispatch Order**:
The stable child-intent order computed for a **Dispatch Batch** after viewer heat, due time, retry penalty, and deterministic tie-breakers are applied. Waiting does not reshuffle the order; later claims continue from this ordered queue.
_Avoid_: fairness aging, dynamic reprioritization, starvation compensation

**Scheduled Run Boundary**:
A runtime boundary that starts scheduled work outside an incoming user HTTP request. It includes **Scheduled Job**, heartbeat, and dream execution, but not cron management API requests.
_Avoid_: cron entry, cron API, scheduler callback

**Managed Background Process**:
An OS child process explicitly started by the **Main Agent** through built-in background-process tools. It can continue after the starting tool call returns, and the same owner scope can later list it, stop it, or read its captured output. A **Managed Background Process** is owned by source, tenant, user, chat session, agent, and workspace context. It is not an async tool task, scheduled job, scheduled run, or agent execution run.
_Avoid_: async task, scheduled job, cron run, background hot patch

**Execution Model Slot**:
An optional model selection pinned to a **Scheduled Job**. If absent, each **Scheduled Run** uses the **Tenant Default Model** at execution time.
_Avoid_: model params, cron model

**Execution Model Fallback**:
The behavior where a **Scheduled Run** uses the current **Tenant Default Model** when its configured **Execution Model Slot** cannot be used. The fallback is silent in the user interface but must remain visible in operational records.
_Avoid_: hard failure, invisible fallback

**Tenant Provider Configuration**:
The tenant-scoped set of LLM provider definitions and model choices available for model selection. One **Tenant Provider Configuration** contains many provider entries and identifies at most one **Tenant Default Model**.
_Avoid_: model cache, global provider list, system model config

**Tenant Default Model**:
The active LLM selection for a tenant, used by agent work when no narrower **Execution Model Slot** is specified.
_Avoid_: global model, system default model

**Empty Model Output**:
A model-call outcome where the provider call succeeds but returns no usable assistant content for the runtime to continue or complete agent work. Text, tool-use, structured content, and reasoning content are all usable model content; empty strings, whitespace-only text, empty lists, and missing content are not. **Empty Model Output** is scoped to model-call handling, not to a whole Scheduled Run or chat turn that merely ends with no visible text.
_Avoid_: output_len=0, blank reply, empty cron output

**Source System Configuration**:
A source-scoped runtime configuration surface for behavior shared by requests from the same external source. It is not a tenant configuration and does not describe user, organization, or workspace identity.
_Avoid_: system feature configuration, system feature config, 系统特性配置, tenant config, user config

**Source Built-in Tool**:
An executable custom tool asset owned by one source and available to every tenant under that source. A Source Built-in Tool is distinct from an Agent Profile's built-in-tool configuration, and no tenant owns or may alter it.
_Avoid_: source tool config, shared tenant tool, tenant tool script

**Source Built-in Tool Contract**:
The AgentScope-compatible callable identity, purpose, and input shape of one Source Built-in Tool. Its identity is a stable restricted tool name, independent of its script filename; the first release establishes it through statically inspectable declarations for a complete tool JSON Schema, credentials, and a Python script with one fixed invocation entry point. Neither the number of active tools nor individual Schema size or complexity is capped.
_Avoid_: free-form script invocation, filename-only tool definition, dynamic Schema, dynamic credential declaration, tool-count quota, Schema complexity quota

**Source Built-in Tool Adapter**:
The Swe-owned adapter that registers a Source Built-in Tool with the regular Toolkit, validates calls against its Source Built-in Tool Contract, invokes the script across its execution boundary, and normalizes the result into the regular tool response contract.
_Avoid_: in-process uploaded script, custom model protocol, raw script result

**Source Built-in Tool Execution Boundary**:
The per-invocation boundary that runs a Source Built-in Tool with only the current tenant's workspace and authorized runtime capabilities. Every call passes the ordinary Tool Guard and approval chain and enforces the Python tenant path guard, resource boundary, and credential declaration; if any guard cannot be established, the call fails closed. The source shares tool code, never tenant data, credentials, or management authority.
_Avoid_: source-wide tenant access, shared credential context, backend-process execution, guard bypass, permissive fallback

**Source Built-in Tool Resource Boundary**:
The resource boundary for a Source Built-in Tool call. It inherits the current tenant's process CPU, memory, and concurrency limits and has the standard sixty-second timeout; a source tool cannot raise those limits.
_Avoid_: source-level resource escalation, unlimited shared tool, script-defined resource cap

**Source Built-in Tool Async Execution**:
The first-release execution mode for Source Built-in Tools. Newly added source tools run synchronously; only an Override of `execute_shell_command` inherits that Agent's existing asynchronous-execution choice.
_Avoid_: general source-tool background mode, source-owned async toggle, lost shell async choice

**Source Built-in Tool Credential Declaration**:
The explicit list of runtime environment variable names a Source Built-in Tool needs. A call receives only the declared values from its current tenant; missing values produce a structured configuration failure, and source or backend credentials are never eligible.
_Avoid_: whole tenant environment, source secret, backend secret, implicit credential access

**Source Built-in Tool Dependency Boundary**:
The first-release rule that a Source Built-in Tool is one Python source file of at most 1 MB, using only the standard library and Swe's fixed runtime interface. It cannot install, bundle, or select third-party dependencies or a custom runtime.
_Avoid_: requirements file, package upload, runtime installation, custom virtual environment, oversized source file

**Source Built-in Tool Safety Gate**:
The mandatory upload scan for every Source Built-in Tool version. A safety finding or unavailable scan rejects publication; source management cannot bypass this gate.
_Avoid_: warning-only publication, scan bypass, unscanned source tool

**Source Built-in Tool Manual Test**:
An explicitly confirmed real execution of an unpublished Source Built-in Tool version using the current Source Tool Administrator's selected Agent Profile, tenant workspace, declared credentials, and JSON input validated against the draft's Contract. Its displayed result uses the normal redaction and output limits; audit excludes test inputs, script content, and credentials. It neither publishes the version nor changes availability for other tenants.
_Avoid_: dry-run, source-wide test, implicit publish, side-effect-free preview, unchecked test input, unrelated Agent context, unbounded test output

**Source Built-in Tool Activation Boundary**:
The start of an Agent run, when it snapshots its effective Source Built-in Tool catalog. Publication, replacement, and deactivation affect the next Agent run only; a running Agent retains its starting catalog.
_Avoid_: mid-run tool mutation, next-call-only reload, retroactive catalog change

**Source Built-in Tool Historical Record**:
The retained scripts, version snapshots, content identities, and audit records for a Source Built-in Tool. The first release permits deactivation but no rollback or permanent deletion of this record.
_Avoid_: destructive source-tool deletion, erased audit trail, rollback history

**Source Built-in Tool Result Boundary**:
The rule that a Source Built-in Tool returns only a JSON-serializable business result. The Source Built-in Tool Adapter turns it into the normal tool response and applies Swe's standard failure, redaction, output-limit, conversation-record, and observability behavior. A runtime failure never falls back to a code-defined built-in, even for an Override.
_Avoid_: script-defined UI card, raw script output, custom error transport, fallback to built-in implementation

**Source Built-in Tool Network Boundary**:
The rule that a Source Built-in Tool may use only the platform's existing network egress policy. It cannot configure or bypass network destinations, and external authentication remains limited to its current tenant's declared credentials.
_Avoid_: source-controlled egress allowlist, network bypass, shared integration credential

**Source Built-in Tool Invocation Attribution**:
The source-tool identity, tool name, and published version or content identity recorded with a standard tool invocation, alongside its tenant, source, Agent, and result. It excludes call arguments, script bodies, and credential values.
_Avoid_: unattributed shared-tool call, logged tool secret, persisted script body

**Source Built-in Tool Change Notification**:
The cross-tenant notification of a Source Built-in Tool publication, replacement, or deactivation. The first release sends none; the change is observable through the next Agent run's effective catalog and source-level audit records.
_Avoid_: tenant broadcast, source-tool change message, silent untraceable change

**Source Built-in Tool Override**:
The precedence rule under which a Source Built-in Tool with the same tool name replaces a Swe code-defined built-in tool for that source. An Override retains the built-in's complete tool JSON Schema while changing only implementation and description. It never overrides a Skill- or MCP-provided tool; such a name collision is invalid.
_Avoid_: registration-order override, Schema-changing built-in override, Skill override, MCP override

**Source Built-in Tool Replacement**:
The explicitly confirmed publication of a staged same-name Source Built-in Tool draft. It is audited and affects later calls only; a call already executing retains the version with which it began.
_Avoid_: retroactive replacement, execution interruption, silent overwrite, unconfirmed replacement

**Source Built-in Tool Draft**:
An unpublished Source Built-in Tool version that has passed static validation and the Source Built-in Tool Safety Gate. A Source Tool Administrator may manually test it or explicitly publish it; it does not change any Agent's effective catalog before publication.
_Avoid_: implicit publication, unscanned test script, active source tool

**Source Built-in Tool Draft Discard**:
The explicit removal of an unpublished Source Built-in Tool Draft by a Source Tool Administrator. It does not remove published tool history; its creation, testing, and discard remain auditable as metadata.
_Avoid_: published-version deletion, unaudited draft removal, source-tool rollback

**Source Built-in Tool Draft Uniqueness**:
The rule that each source and tool name has at most one unpublished Source Built-in Tool Draft. A later upload must explicitly replace or discard the existing draft before it can become the sole draft.
_Avoid_: multiple pending versions, ambiguous publication target, parallel draft set
**Source Built-in Tool Availability**:
The source determines which Source Built-in Tools are available to an Agent, while the Agent's own enabled or disabled choice determines whether an available tool is callable for that Agent. An Override replaces implementation only and cannot bypass a disabled choice.
_Avoid_: source-forced enablement, override bypass, tenant implementation ownership

**Source Built-in Tool Default Enablement**:
A newly published non-conflicting Source Built-in Tool is initially enabled for every Agent under its source through lazily resolved source defaults, without bulk-writing Agent configuration. Each Agent may later disable it through its own tool configuration.
_Avoid_: opt-in-only source tool, permanently forced tool, bulk tenant configuration write

**Source Built-in Tool Agent Choice Persistence**:
An Agent's explicit enabled or disabled choice for a Source Built-in Tool survives that tool's source-level deactivation and later reactivation. Only an Agent that has never encountered the tool receives its default enablement.
_Avoid_: reactivation reset, source-forced re-enable, forgotten Agent choice

**Source Built-in Tool Catalog Exposure**:
The complete registration of every source-enabled Source Built-in Tool that the Agent has not disabled when an Agent run begins. It is not filtered by user intent, keywords, or on-demand discovery.
_Avoid_: lazy source tool, keyword-selected tool, partial source catalog

**Source Tool Library**:
The source-scoped management collection of Source Built-in Tools. It is presented within the Source System Configuration page but has independent storage and lifecycle from Source System Configuration. Its first release accepts complete-file upload and same-name replacement, not browser-based script editing, and does not cap the number of enabled Source Built-in Tools.
_Avoid_: source configuration JSON, agent tool list, tenant script library, browser script editor, source tool-count quota

**Source Tool Library Storage**:
The Swe-controlled, source-isolated storage of Source Built-in Tool scripts and their version history. It is separate from Marketplace storage while retaining atomic publication, content identity, and audit history.
_Avoid_: Marketplace item storage, tenant workspace storage, Source System Configuration storage, rollback store

**Source Built-in Tool Script Read Access**:
The read-only viewing or download of current and historical Source Built-in Tool scripts by a Source Tool Administrator. Ordinary tenants may see effective tool metadata but not script content.
_Avoid_: tenant script download, browser editing, public source code

**Source Built-in Tool Deactivation**:
The source-level withdrawal of a Source Built-in Tool. It affects later calls only: a deactivated Override restores the code-defined built-in, while a deactivated unique source tool is unavailable; historical versions and audit records remain for tracing only.
_Avoid_: destructive deletion, interrupted call, disabled Agent tool, rollback

**Source Built-in Tool Failure Availability**:
The rule that a runtime failure of a Source Built-in Tool affects only that invocation and does not deactivate the tool. Source-level availability changes only through an explicit Source Tool Administrator action.
_Avoid_: automatic circuit-breaker deactivation, failure-driven source mutation, implicit source disablement

**Source Tool Administrator**:
The manager or administrator authorized for the current source and permitted to upload or replace a Source Built-in Tool. A tenant administrator may use such a tool but may not manage it.
_Avoid_: tenant tool administrator, any tenant uploader

**Source System Configuration Override**:
A value explicitly saved in **Source System Configuration** that replaces the corresponding broader runtime setting for requests from that source. Missing values are inheritance, not implicit overrides.
_Avoid_: source default, tenant override, page default

**Runtime Request Identity**:
The tenant and source context that determines which runtime configuration and model selection a request observes. One **Runtime Request Identity** resolves to one **Tenant Provider Configuration** view for provider and active-model reads.
_Avoid_: cache key, auth header set, iframe context

**Background SubAgent Launch Identity**:
The **Runtime Request Identity** carried from the Main Agent runtime into a **Background SubAgent Run** so the worker observes the same source-scoped runtime configuration and model selection as its parent run.
_Avoid_: effective tenant only, provider cache key, worker tenant

**Tenant Scaffold Bootstrap**:
The tenant setup state in which a runtime scope has the required tenant-local workspace structure and baseline files. A **Tenant Scaffold Bootstrap** does not imply that the first-run conversational onboarding has happened.
_Avoid_: chat bootstrap, BOOTSTRAP.md flow, onboarding chat

**Bootstrap Chat Flow**:
The first-run conversational onboarding in which an Agent learns and records identity, style, and user preferences. A **Bootstrap Chat Flow** is separate from **Tenant Scaffold Bootstrap** and may be skipped for a tenant that still has a valid scaffold.
_Avoid_: tenant bootstrap, scaffold bootstrap, workspace initialization

**Disabled Skill**:
A managed skill package retained by the control plane but excluded from the **Skill Runtime View** and ordinary Agent skill discovery for later runs. Disabled status alone is not a filesystem security boundary.
_Avoid_: hidden skill, unregistered skill, inactive skill

**Disabled Skill Store**:
A Workspace-scoped retention area for **Disabled Skill** packages outside the conventional runtime skill path. It is managed through skill-management surfaces but remains ordinary filesystem content that generic file or shell searches may discover.
_Avoid_: skill sandbox, secure skill store, deleted skills

**Skill Management State**:
The authoritative backend-managed record of installed skills, enablement, channel availability, and configuration for one Workspace. It is accessed through skill-management surfaces rather than ordinary Workspace browsing, search, or editing.
_Avoid_: workspace skill file, user-editable skill manifest, runtime skill list

**Skill Management Surface**:
A user-visible service or API that performs a managed skill lifecycle operation, including enablement, disablement, deletion, re-import, distribution, or editing. It resolves a registered package from **Skill Management State** to either the **Skill Runtime View** or **Disabled Skill Store**; a surface may write enablement state and rely on later reconciliation for package placement when that is its established service boundary. Market may also perform an **Explicit Skill Claim**.
_Avoid_: skill-directory browser, active-directory-only management surface

**Managed Skill Package Resolution**:
The management-surface rule for locating a registered package from its **Skill Management State**. It prefers the root selected by enablement and falls back to the other managed root during a **Skill State Conflict**. An **Active Collision Promotion** takes precedence when both copies exist. A Market mutation receives both the resolved package and an explicit promotion result: it is true only when the collision changes a registered skill from disabled to enabled, so only that case requires the one Agent reload. It does not resolve **Unmanaged Skill Content** that has no registered-name collision.
_Avoid_: enumerate every skill-looking directory, manifest-only package lookup

**Active Collision Promotion**:
The default resolution of a same-name active and disabled package: the `skills/` package is retained as the **Canonical Skill Package**, the `.disabled_skills/` package is deleted, and the registered skill becomes enabled. SWE reconciliation and Market explicit management both apply this rule.
_Avoid_: preserve disabled state on active collision, ambiguous duplicate skill

**State-Preserving Distribution**:
Market distribution that installs an unregistered skill as enabled, but updates an already registered package at its managed location without changing its enablement. In particular, updating a **Disabled Skill** does not make it part of the **Skill Runtime View**.
_Avoid_: update means enable, replace-active-directory-only

**Disabled Skill Maintenance**:
Management-surface viewing, downloading, editing, and publishing of a **Disabled Skill** at its resolved package location. Maintenance changes package content or related metadata but does not change enablement.
_Avoid_: disabled means immutable, maintenance means enable

**Canonical Skill Package**:
The authoritative package content when the same skill exists in both the **Skill Runtime View** and **Disabled Skill Store**. The runtime-view copy wins for content; **Active Collision Promotion** is the exception to ordinary **Skill Management State**-driven placement and changes the registered skill to enabled.
_Avoid_: newest skill copy, enabled skill state, manifest-selected content

**Skill State Conflict**:
A disagreement between **Skill Management State** and the retained location of a skill package. A skill in conflict is unavailable to Agent Runs until the disagreement is reconciled.
_Avoid_: partially enabled skill, best-effort skill state, usable mismatch

**Unmanaged Skill Content**:
Workspace content that resembles a skill package but has no entry in **Skill Management State**. It is neither registered nor governed by disabled-skill discovery guarantees, even when it remains visible to model-initiated file or shell tools. Market may retain its legacy list, viewing, download, editing, publishing, and direct-delete behavior for this ordinary content; only an **Explicit Skill Claim** creates managed state, except that a same-name registered disabled package triggers **Active Collision Promotion**.
_Avoid_: disabled skill, automatically installed skill, runtime skill

**Explicit Skill Claim**:
A user-initiated Market enablement of **Unmanaged Skill Content** in the ordinary skill directory. After the established security scan, it creates the corresponding **Skill Management State** entry as enabled. Except for **Active Collision Promotion**, SWE never claims unmanaged content automatically, and the **Disabled Skill Store** contains only registered packages.
_Avoid_: automatic skill discovery, reconciliation registration, disabled-skill import

**Skill Runtime View**:
The current set of registered and enabled skill packages selected from a Workspace's ordinary skill directory. It excludes **Unmanaged Skill Content**, changes immediately when skill enablement changes, and gives existing Agent Runs no guarantee that earlier skill files remain available.
_Avoid_: skill snapshot, immutable skill view, complete skill directory

**Console Skill Selection Panel**:
The command-style panel opened by `@` in Console chat for selecting ordered **User-Selected Skills**, including duplicates, from the current **Skill Runtime View**. A selection is represented both by an **Inline Skill Tag** in the message and by trusted structured selection context; the panel does not list built-in tools, MCP tools, or other callable runtime capabilities.
_Avoid_: tool panel, MCP menu, all-capabilities menu

**Inline Skill Tag**:
The visible, atomic `@` label for one **User-Selected Skill** occurrence inside a Console chat message, created only by confirmation in the **Console Skill Selection Panel**. It is user-message content for readability, but does not replace the trusted structured selection context that resolves the selected skill; deleting the tag removes its corresponding selection occurrence as well.
_Avoid_: trusted skill directive, tool call, execution proof

**User-Selected Skill**:
A **Skill Runtime View** member that a user explicitly selects for a single chat turn and remains available when that turn starts. A turn may contain repeated **User-Selected Skills**; their **Skill Use Directives** are injected in selection order after duplicate runtime identifiers are removed. Each selection records user intent as structured turn context with a readable message marker, but is not evidence that the skill actually executed.
_Avoid_: skill mention, forced tool call, permanently active skill, single selected skill

**Explicit Skill Selection Activation**:
The session-scoped activation of a **User-Selected Skill** after the server validates its structured selection against the current **Skill Runtime View** and resolves its readable `SKILL.md`. It loads that skill's Hooks after the current turn's `UserPromptSubmit` and `SessionStart` events, before subsequent tool calls, and persists them for the rest of the session; it does not establish **Actual Skill Use**, set a current skill, create a skill invocation trace, or prove the model read the skill document.
_Avoid_: plain-text skill mention, filename match, automatic semantic inference, confirmed skill use

**Skill Runtime Identifier**:
The stable `name` of a skill package in one Workspace: its managed skill-directory name and **Skill Management State** key. It is the identity used for runtime selection, channel availability, and injection de-duplication; a frontmatter or market `skill_id` is not a substitute.
_Avoid_: display name, frontmatter name, market skill id

**Skill Use Directive**:
A trusted instruction block for one **User-Selected Skill** whose server-resolved `SKILL.md` exists and is readable. It names the skill, describes it, and supplies that path; it requires the Agent to read the document before acting, but does not include the document's full content. With multiple directives, every document is read in directive order before task execution begins.
_Avoid_: skill prompt copy, user-supplied file path, complete skill document

**Skill-Use Enforcement**:
The runtime policy that verifies an Agent followed a **Skill Use Directive** before it acts. The first rollout has no Skill-Use Enforcement; the directive is a trusted model instruction rather than a runtime gate.
_Avoid_: prompt injection, tool attribution, guaranteed skill execution

**Actual Skill Use**:
The runtime-detected participation of a skill in a turn, established only by reading its resolved `SKILL.md` or by a tool input that targets an asset under its resolved skill directory. It is distinct from **User-Selected Skill** and is the only basis for tool-call skill attribution.
_Avoid_: selected skill, requested skill, assumed skill invocation, filename suffix match, keyword match

**Non-Authoritative Skill Signal**:
A file suffix, prose-derived keyword, tool hint, tool sequence, or MCP server name associated with a skill. It may support offline analysis but never activates, continues, attributes, or loads Hooks for a skill at runtime.
_Avoid_: activation evidence, continuation evidence, attribution evidence, hook trigger

**Skill Asset Evidence**:
A tool input that resolves to a path inside one enabled skill's effective directory. It may establish **Actual Skill Use**, but loads that skill's Hooks only when the skill was already explicitly selected or its resolved `SKILL.md` was read in the session.
_Avoid_: extension match, text substring, arbitrary workspace path, hook bootstrap

**Session Skill Hook Order**:
The deterministic hook order for a session with explicitly selected skills: tenant Hooks, then Agent Profile Hooks, then one deduplicated Hook source for each selected skill in its first-selection order. Later selections append only previously unloaded skills; normal Hook result merging resolves conflicts.
_Avoid_: arbitrary hook order, repeat-selection duplication, last-selected-first execution

**Unavailable Skill Selection**:
A user-requested skill choice that is no longer in the **Skill Runtime View** when its chat turn starts. The choice is discarded without skill guidance or selection-based attribution, while other **User-Selected Skills** in the same turn may still apply; the turn is ordinary chat only when none remain.
_Avoid_: failed chat turn, disabled skill invocation, deferred selection, auditable selection

**Skill Isolation Guarantee**:
The stronger platform-independent boundary under which disabled skill content is inaccessible to model-initiated tools on every supported operating system. **Skill Isolation Guarantee** is distinct from **Skill Discovery Suppression**.
_Avoid_: best-effort skill hiding, platform-specific skill safety, shell path filter

**Skill Discovery Suppression**:
The default disabled-skill behavior that removes a package from Agent registration, prompting, and conventional skill-directory discovery. It reduces accidental reuse but does not deny generic file searches or deliberately crafted shell access.
_Avoid_: skill isolation, filesystem sandbox, disabled-skill authorization

**Runtime Invocation Claims**:
Session, trace, tenant, and source claims that Swe passes across a runtime invocation boundary for a receiving tool or integration to interpret inside an already trusted channel. **Runtime Invocation Claims** are distinct from **Runtime Request Identity**, which is internal request context, and are not independently verifiable credentials.
_Avoid_: runtime metadata, env/header info, credential, signed token

**Execution Trace ID**:
The unique identifier for one Swe execution. Spans, Subtasks, execution records, feedback, and Runtime Invocation Claims correlate through this identifier even when several executions share one external distributed trace.
_Avoid_: B3 trace ID, batch ID, request header trace ID

**B3 Trace ID**:
The external distributed-tracing identifier received through B3 transport metadata. It may be shared by multiple executions in one Dispatch Batch and therefore is not an execution identity.
_Avoid_: execution trace ID, Subtask trace ID, unique run ID

**Canonical Runtime Claim Name**:
The preferred external name for one **Runtime Invocation Claim** at a specific transport boundary. Canonical names are stable and transport-appropriate; compatibility aliases may exist only for boundaries that already require them.
_Avoid_: env/header info, arbitrary key, passthrough name

**Runtime Scope Claim**:
The **Runtime Invocation Claim** that names the resolved runtime isolation scope for a call, derived from the current tenant and source context when such a scope exists. A **Runtime Scope Claim** complements the logical tenant and source claims; it does not replace either one.
_Avoid_: tenant id, source id, effective tenant

**Tenant Runtime Environment Variable**:
A tenant-controlled key/value configured for exactly one **Runtime Request Identity** and supplied only at permitted runtime boundaries. It is not a process environment value, **System Configuration Environment Key**, or **Runtime Invocation Claim**.
_Avoid_: process env, backend env, global environment variable

**Runtime-Owned Claim Name**:
A claim name reserved for Swe-issued **Runtime Invocation Claims** at an invocation boundary. A **Runtime-Owned Claim Name** cannot be supplied or overridden by tenant env, tool config, passthrough headers, or handler config.
_Avoid_: user env key, custom header, configurable claim

**Runtime Invocation Claims Context**:
The backend-local execution context that carries the current **Runtime Invocation Claims** to nested tool and integration launch points during one agent run. A **Runtime Invocation Claims Context** is not itself transmitted outside Swe.
_Avoid_: global env, request identity, credential store

**System Configuration Environment Key**:
A backend-owned configuration key used by Swe itself. A **System Configuration Environment Key** is not part of user-controlled runtime env and must not be exposed through user-invoked tool subprocesses.
_Avoid_: user env, tenant env, ordinary shell env

**User Tool Subprocess Environment**:
The environment visible to a subprocess started by a user-invoked tool such as shell execution. A **User Tool Subprocess Environment** may include safe process basics and scoped runtime env, but excludes **System Configuration Environment Keys** and runtime boundary keys that expose or alter isolation internals.
_Avoid_: process env, backend env, system environment

**Built-in Shell Execution**:
The user-invoked shell command execution path owned by Swe for a tenant-scoped request. **Built-in Shell Execution** is distinct from MCP `stdio` server launches and platform maintenance subprocesses.
_Avoid_: arbitrary subprocess, MCP stdio launch, maintenance worker

**Tenant Process Resource Limits**:
A tenant-scoped policy that caps per-process CPU time and memory consumption for in-scope tenant subprocess launches. **Tenant Process Resource Limits** reduce host resource exhaustion risk; they are not a command intent classifier, command blacklist, or process-group aggregate resource budget.
_Avoid_: command blacklist, shell denylist, resource timeout, process group quota

**Process Limit Exceeded**:
A tool failure outcome where a subprocess is terminated or fails because **Tenant Process Resource Limits** were applied. **Process Limit Exceeded** is distinct from a wall-clock timeout and from an ordinary shell command failure.
_Avoid_: timeout, shell failed, command denied

**Tenant Shell Execution Slot**:
A per-tenant concurrency allowance for one in-flight **Built-in Shell Execution**. A **Tenant Shell Execution Slot** is held until the shell tool returns and its Unix process group cleanup has completed; it is not a count of every OS process forked by a script.
_Avoid_: process count, PID quota, subprocess total

**Shell Concurrency Limit Exceeded**:
A tool failure outcome where **Built-in Shell Execution** cannot start because the tenant has no available **Tenant Shell Execution Slot** within the configured wait period. **Shell Concurrency Limit Exceeded** is distinct from **Process Limit Exceeded**, because no shell subprocess has been launched yet.
_Avoid_: process limit exceeded, timeout, queue full

**Mandatory Console Channel**:
The built-in **Console Channel** is a runtime invariant that is always treated as enabled for every agent and tenant, including when no explicit channel entry has been saved yet. Users may configure its other fields, but persisted, imported, or interactive configuration must not disable it.
_Avoid_: optional console, disabled console, console toggle

**Channel Management Constraint**:
A system-managed channel rule that remains visible in channel management and tells clients which channel state is enforced rather than user-editable. A **Channel Management Constraint** may lock one field while leaving the rest of the channel configurable.
_Avoid_: frontend-only hardcode, hidden channel rule, implicit UI behavior

**Console Output Suppression**:
A runtime-only behavior that temporarily suppresses terminal printing in a specific execution path. **Console Output Suppression** does not change **Mandatory Console Channel** state and is not part of channel management.
_Avoid_: disabled console channel, channel off, console config

**Historical Tool Result Compaction**:
A conversation-history cleanup behavior that shortens previously stored tool results so the Main Agent can continue within context limits. It is separate from truncating the first result returned by a tool call.
_Avoid_: tool output truncation, file read truncation, live tool truncation

**File Read Truncation**:
A source-scoped limit on text returned by file-reading tools during the same turn that reads the file. It is separate from **Historical Tool Result Compaction**.
_Avoid_: file compaction, historical tool result compaction

**Tool Output Controls**:
The user-facing grouping for source-scoped controls over historical tool-result compaction and file-read output truncation.
_Avoid_: tool result compression configuration

**Context Window**:
The bounded model input budget available to a Main Agent turn. A **Context Window** is measured as the configured capacity used to decide whether the next turn can fit its prompt, memory, conversation history, and current user input.
_Avoid_: token bill, monthly quota, historical usage

**Persisted Context Occupancy**:
An estimate of how much of the **Context Window** is occupied by the persisted state and fixed runtime context that would actually enter the next Main Agent model input after any completed compaction. It includes system prompt, completed compressed summary, effective history messages, and compacted tool results; it excludes unsent composer text, already-compacted raw history, and tokens already billed by previous model calls.
_Avoid_: token usage, usage statistics, cost usage

**Tool Call Status**:
The user-visible lifecycle state of one user-visible tool invocation during a Main Agent run. A **Tool Call Status** describes an individual tool invocation as running, successful, or failed; failed means the tool itself failed, not that the user stopped or cancelled the overall Main Agent run. The start of a tool invocation carries the running status, and the tool's returned output carries the successful or failed terminal status.
_Avoid_: tool event status, frontend tool result, trace status

**Tool Output Frame**:
A live, user-visible presentation update for textual output produced while one tool invocation is still running. A **Tool Output Frame** belongs to exactly one **Tool Call Status** lifecycle, preserves its output source when known, is ordered only within that tool invocation, is not visible to the Main Agent as model context, and is not itself the final tool result remembered by the Main Agent.
_Avoid_: partial tool result, durable output chunk, tool memory frame, streaming object result

**Live Tool Output Area**:
The user-visible region inside a tool card where **Tool Output Frames** for that tool invocation are rendered during execution. A **Live Tool Output Area** is part of the tool presentation, not a separate assistant message in the conversation, and the final tool result becomes the card's authoritative output when it arrives.
_Avoid_: log chat message, separate output bubble, global tool log

**Terminal Tool Result Precedence**:
The rule that a successful or failed final tool result replaces the **Live Tool Output Area** as the authoritative tool-card output. If a tool is cancelled without a final result, the card may keep the last live output as cancellation context.
_Avoid_: live output as final result, partial result precedence

**Live Tool Output Guard**:
The narrow runtime protection applied before **Tool Output Frames** are sent for live presentation. A **Live Tool Output Guard** controls live output eligibility, live display limits, live replay limits, source preservation, and required redaction for real-time frames without replacing the existing final tool-result rules.
_Avoid_: tool output policy, final result policy, historical compaction policy

**Live Stream Replay**:
The best-effort restoration of live presentation events for a Main Agent run that is still active when the user reconnects. **Live Stream Replay** may include **Tool Output Frames** from the active run, but it is not historical recovery after the run has ended.
_Avoid_: chat history replay, durable tool log, completed-run output restore

**Tool Error Summary**:
A user-visible, bounded explanation attached to a failed **Tool Call Status**. A **Tool Error Summary** is not an audit record, diagnostic log, or full raw tool failure.
_Avoid_: raw tool error, tool failure log, audit error

**Tool Execution Error**:
An explicit runtime exception raised by a tool or tool-adjacent runtime path to declare that the tool invocation itself failed. A **Tool Execution Error** carries canonical failure semantics and is not just an arbitrary Python exception or plain-text output string.
_Avoid_: generic exception, plain-text tool failure, error string

**Structured Tool Failure Result**:
A persisted `tool_result` failure payload encoded in the MCP-style shape with `isError=true` and failure content blocks. A **Structured Tool Failure Result** is the canonical terminal output for failed tool invocations across local tools, MCP tools, and runtime-generated failures.
_Avoid_: plain-text failure output, ad-hoc error JSON, inferred tool failure

**MCP Availability Failure**:
A failure that prevents an enabled MCP client from becoming usable by an Agent, including failure to connect or discover its available capabilities. An **MCP Availability Failure** is distinct from an individual MCP tool invocation returning a **Structured Tool Failure Result**.
_Avoid_: MCP tool failure, optional MCP skip, successful connection log

**Hook Telemetry Event**:
A structured observability record for one Hook Runtime boundary, used to analyze hook behavior without changing the hook's runtime decision semantics. A **Hook Telemetry Event** includes the boundary-level outcome and the handler-level details that explain it, and is emitted in a log-collection-friendly shape rather than persisted as a Trace Span.
_Avoid_: debug log, audit record, raw hook payload, trace span

**Hook Telemetry Log Message**:
A single-line structured application log message with a stable hook telemetry prefix and a JSON payload. **Hook Telemetry Log Message** is a normal operational signal, not an exceptional alert, and does not imply changing the global log formatter.
_Avoid_: global JSON logging, unstructured hook log, trace span, warning log

**Hook Telemetry Emission Boundary**:
The rule that a **Hook Telemetry Log Message** is emitted only when at least one hook handler actually runs for a Hook Runtime boundary.
_Avoid_: unmatched hook boundary log, resolver miss telemetry

**Hook Telemetry Correlation**:
The relationship between a **Hook Telemetry Log Message** and the request or trace that caused it. **Hook Telemetry Correlation** should include a trace identifier when one is available, but a missing trace identifier does not make the telemetry event invalid.
_Avoid_: mandatory trace span linkage, uncorrelated hook log

**Hook Telemetry Schema**:
The versioned JSON shape inside a **Hook Telemetry Log Message**. The schema records correlation fields, boundary-level outcome fields, and handler-level details while excluding raw hook payloads by default.
_Avoid_: ad-hoc log fields, raw payload schema, trace span schema

**Application Log Output Pipeline**:
The operational path that carries Swe application log records from runtime emission to process-visible outputs. An **Application Log Output Pipeline** transports ordinary and structured log records without changing their domain meaning or schema.
_Avoid_: telemetry schema, audit log, business operation log, tool output frame

**Hook Boundary Outcome**:
The merged result of one Hook Runtime boundary after all matching handlers have been resolved and combined.
_Avoid_: handler result, raw hook output, final log line

**Hook Handler Detail**:
The observable result of one hook handler within a **Hook Telemetry Event**, kept so slow, failed, blocking, or input-mutating handlers can be diagnosed. **Hook Handler Detail** stores structured metadata and redacted, bounded previews rather than full handler input or output.
_Avoid_: hook boundary outcome, raw handler payload

**Hook Payload Preview**:
A redacted and size-bounded representation of hook-adjacent text or structured data used for diagnosis without retaining the original payload.
_Avoid_: raw prompt, raw tool input, raw tool output, full updated input

**Current Tool Response**:
The successful output produced by the current tool invocation for the active `PostToolUse` boundary. A **Current Tool Response** is the tool's business output, not the full persisted `tool_result` block and not a **Hook Conversation Snapshot**.
_Avoid_: full tool result block, conversation snapshot, AgentScope acting return value

**PreToolUse Terminal Stop**:
A `PreToolUse` hook outcome with the explicitly returned `stop` decision, expressed as `{"decision":"stop","reason":"…"}` and available to every handler type, that rejects the pending tool invocation and ends the current Main Agent turn without another model call. The first `stop` in handler order is authoritative and cannot be replaced by another decision or input update; handler failures and `failPolicy:block` never imply it. Its reason, or the stable fallback `Hook requested stop`, is always emitted and persisted as the turn's final assistant message while the failed tool result remains available for tool presentation and audit as `hook_stopped`. It blocks unstarted peer calls and requests best-effort cancellation of already-started peer calls; it does not promise rollback of external side effects. It bypasses the later `Stop` hook. It is distinct from `deny` and `block`, which reject the invocation but allow the Main Agent to choose a different next action.
_Avoid_: terminal deny, blocked tool, cancelled session

**PostTool Terminal Stop**:
A `PostToolUse` or `PostToolUseFailure` hook outcome with the explicitly returned `stop` decision, expressed as `{"decision":"stop","reason":"…"}`, that ends the current Main Agent turn after the tool outcome is known. It requests best-effort cancellation of unfinished peer calls while retaining completed outcomes and without promising external rollback. It records the completed tool outcome and post-hook context before the final assistant reason, then bypasses the `Stop` hook. It does not rewrite the completed tool outcome; for a failed tool, it replaces propagation of the original tool exception while retaining that failure for presentation and audit. Hook failure, `failPolicy:block`, `deny`, and `block` never imply it. It is distinct from `deny` and `block`, which remain non-terminal for post-tool events.
_Avoid_: post-tool denial, tool rollback, completed session

**Hook Conversation Snapshot**:
A bounded hook-facing snapshot of the current session's message list at one Hook Runtime boundary, including normal user, assistant, tool-call, and tool-result messages while excluding reasoning content. A **Hook Conversation Snapshot** is not the saved transcript file and is not the full Agent state.
_Avoid_: full context, transcript contents, agent state dump, reasoning trace

**Session Skill Freshness**:
The cross-turn behavior that determines when a chat session starts using updated skill content. In this context, **Session Skill Freshness** means skill changes take effect on the next turn, not during an in-flight turn.
_Avoid_: skill hot reload, mid-turn skill reload, live skill patch

**Skill Directory Revision**:
The content identity of one skill across its full directory tree, including `SKILL.md`, scripts, references, and other skill-owned files. A **Skill Directory Revision** changes when any tracked file in that skill directory changes.
_Avoid_: SKILL.md version, single-file skill update, prompt-only skill change

**Skill Directory Freshness Token**:
A lightweight change marker for one skill directory, derived from a stable digest of each tracked file's relative path, `mtime_ns`, and size rather than strict content hashing. In this context, next-turn skill freshness checks compare the stored **Skill Directory Freshness Token** to the current one and accept heuristic rather than exact change detection.
_Avoid_: strict content revision, canonical content identity, cryptographic signature

**Session Associated Skill Set**:
The set of skills that a chat session has already depended on through explicit declaration, detector activation, or direct skill-file reading. **Session Skill Freshness** applies only to this **Session Associated Skill Set**, not to every enabled skill.
_Avoid_: all enabled skills, global active skills, workspace skill set

**Session Skill Snapshot**:
A session-state record that stores the session's **Session Associated Skill Set** together with each skill's last known **Skill Directory Freshness Token**. The **Session Skill Snapshot** is the persisted basis for cross-turn freshness checks.
_Avoid_: trace-derived skill history, transient detector state, prompt-only cache

**Skill Freshness Refresh**:
The next-turn refresh step that rebuilds prompt state and requires the model to re-read the current `SKILL.md` when a stored **Session Skill Snapshot** no longer matches the latest **Skill Directory Freshness Token**.
_Avoid_: mid-turn reload, background hot patch, user-visible skill reset

**Skill Freshness Notice**:
An internal model-facing notice added on the next turn after a **Skill Freshness Refresh**. A **Skill Freshness Notice** uses cautious wording such as detecting a skill-directory change, tells the model that current skill content supersedes assumptions formed from earlier turns, and requires the model to re-read the current `SKILL.md` before relying on that skill. It references the skill path instead of inlining the skill body, can explicitly name a directory switch, and is not exposed to the Console stream or persisted into chat history.
_Avoid_: user-visible message, persistent banner, historical chat message, silent refresh only

**Confirmed Skill Association**:
The point at which a skill becomes part of the session's durable dependency set because the runtime actually activated it, rather than merely suspecting it. Only a **Confirmed Skill Association** can add a skill to the **Session Associated Skill Set**.
_Avoid_: low-confidence guess, enabled-skill membership, possible skill match

**Market Skill Owner Set**:
The current set of users who own a market skill within one source, as resolved by market skill owner reverse lookup. A **Market Skill Owner Set** is based on current user skill state and is not a historical distribution audit; readiness workflows resolve this set server-side so the displayed owner list and checked user set share the same source of truth.
_Avoid_: assigned users, distribution history, skill install log

**Skill Readiness Skill Id**:
The `skill_id` value used to find readiness configuration and related scheduled jobs for a market skill. A **Skill Readiness Skill Id** normally comes from the market-provided skill id; before that id exists, the market skill's stable `skill_name` may be used as a fallback value while keeping the field name `skill_id`; allowed values use only letters, digits, underscore, hyphen, dot, and colon.
_Avoid_: skill_key, display name, version, historical distribution id

**Skill Readiness Configuration**:
A runtime configuration keyed by **Skill Readiness Skill Id** that declares which readiness checks apply to a market skill and what parameters those checks use. A **Skill Readiness Configuration** is stored as runtime configuration, not as a deployment-local YAML file; source identity belongs to readiness execution and result isolation rather than the base configuration key.
_Avoid_: static checklist, local YAML, global skill rule

**Skill Readiness Run**:
One asynchronous execution that checks the full **Market Skill Owner Set** for one **Skill Readiness Skill Id** within a specific source. A **Skill Readiness Run** uses `source_id` to resolve the user set, user runtime directories, scheduled jobs, credentials, and result isolation.
_Avoid_: configuration lookup, frontend scan, historical distribution audit

**Skill Readiness Run Progress**:
The observable progress counts for a **Skill Readiness Run**. `failed_users` means users whose readiness result is abnormal, not backend task failures.
_Avoid_: backend failure count, transport error count

**Skill Readiness Run Status**:
The lifecycle state of a **Skill Readiness Run** as shown to administrators. `partial` means some user results are available while non-fatal lookup or check failures prevented a fully complete run.
_Avoid_: backend process status, HTTP request status

**Skill Readiness User Result**:
The readiness outcome for one user inside a **Skill Readiness Run**. A **Skill Readiness User Result** is abnormal when any configured readiness check for that user fails.
_Avoid_: tenant health, backend task result, owner lookup row

**Skill Readiness Check Status**:
The normalized outcome of one readiness check. A check is `pass`, `fail`, or `skip`; technical errors are represented as `fail` with an explanatory message and details rather than a separate status.
_Avoid_: error status, exception category, backend failure class

**Skill Readiness Check Name**:
The stable strategy name of one readiness check inside configuration and results. New readiness check types extend this name registry and generic result payloads rather than adding per-check database columns or per-check APIs.
_Avoid_: KPI, metric column, hard-coded result field

**Profile Identity Block**:
The fixed user identity section appended to `PROFILE.md` through the agent initialization API, containing fields such as branch id, outlet organization id, position id, and customer manager id. A **Profile Identity Block** is distinct from free-form profile memories or general user preference notes.
_Avoid_: arbitrary profile content, memory note, full user info API payload

**Skill Readiness Job Binding**:
The relationship between a **Scheduled Job** and one or more **Skill Readiness Skill Id** values. A paused **Scheduled Job** still counts as a binding, while a disabled job does not count as executable for readiness checks; copied or broadcast jobs preserve the binding unless explicitly changed.
_Avoid_: skill_key binding, skill distribution record, cron tag

**Missing Associated Skill**:
An associated skill whose previously recorded directory can no longer be resolved at freshness-check time. In this context, a **Missing Associated Skill** does not trigger a refresh or notice by itself, and its snapshot entry is silently removed.
_Avoid_: failed refresh, implicit invalidation, required user repair

**Applied Skill Snapshot**:
The refreshed **Session Skill Snapshot** written immediately after a turn detects and applies a **Skill Freshness Refresh** and any one-turn **Skill Freshness Notice**. An **Applied Skill Snapshot** prevents the same freshness-token change from re-triggering on later turns.
_Avoid_: end-of-turn-only snapshot, pending snapshot, repeated refresh marker

**Session Skill Snapshot Record**:
One top-level session-state record, stored alongside other runner-managed state rather than inside agent memory state. In this context, the **Session Skill Snapshot** is a dedicated session-state key.
_Avoid_: agent memory field, embedded agent state, prompt state blob

**Session Skill Snapshot Entry**:
One persisted association record inside the **Session Skill Snapshot**, containing at least `skill_name`, `resolved_skill_dir`, and `freshness_token`. The entry tracks the concrete skill directory that the session previously depended on.
_Avoid_: name-only skill record, manifest-only reference, implicit directory lookup

**Immediate Skill Snapshot Capture**:
The persistence rule that writes a **Session Skill Snapshot Entry** as soon as a **Confirmed Skill Association** happens within the current turn. It does not wait for turn completion.
_Avoid_: end-of-turn batch write, delayed baseline capture, next-turn first write

**Associated Skill Directory Switch**:
The case where the same `skill_name` resolves to a different `resolved_skill_dir` than the one stored in the session snapshot. In this context, an **Associated Skill Directory Switch** counts as an effective skill change.
_Avoid_: name-only identity match, ignored source switch, path-agnostic reuse

**Associated Skill Withdrawal**:
The case where a previously associated skill is still present on disk but is no longer part of the current turn's effective skill set. In this context, an **Associated Skill Withdrawal** counts as an effective skill change, triggers refresh/notice, and removes the snapshot entry.
_Avoid_: silent disable drift, missing-skill ignore case, stale effective skill

**Aggregated Skill Freshness Notice**:
One per-turn **Skill Freshness Notice** that combines all effective associated-skill changes detected for that turn. It lists affected skills item-by-item instead of emitting separate notices per skill.
_Avoid_: per-skill notice spam, repeated freshness banners, fragmented model notice

**System Runtime Diagnostic**:
A periodic, Runtime Instance-scoped assessment of the Swe backend service's load, responsiveness, process resources, and storage capacity. It is broader than a liveness probe and does not execute an Agent Heartbeat.
_Avoid_: self-check, health endpoint, Agent Heartbeat

**Liveness Probe**:
A Runtime Instance signal that only proves the backend request-serving process can answer immediately. A **Liveness Probe** is not a dependency check and must not describe tenant, workspace, source configuration, database, Agent runtime, or scheduled work availability.
_Avoid_: readiness check, system self-check, health diagnostic

**Request Execution Load**:
The current load and responsiveness of the backend request-serving runtime within one Runtime Instance. It prioritizes timely request handling, streaming progress, cancellation, timeout, and scheduled-run coordination over raw throughput, and is distinct from tenant or business-runtime usage.
_Avoid_: Flask worker usage, ordinary HTTP throughput, request latency, tenant usage statistics, Agent Run count, LLM load

**Runtime Instance**:
One running Swe service container in a multi-instance deployment, independently from the business-facing instances used for user allocation.
_Avoid_: business instance, tenant, Supervisor process

**Diagnostic Run**:
One System Runtime Diagnostic collection performed by a Runtime Instance.
_Avoid_: latest-only snapshot, request-time probe, liveness response

**Diagnostic Flow Record**:
One append-only record containing the metrics collected by one Runtime Instance during one Diagnostic Run. It supports latest-state queries and historical trend analysis.
_Avoid_: EAV diagnostic item, JSON payload, LONGTEXT payload, diagnostic run ID

**Runtime Diagnostic Log**:
A machine-readable event emitted by Swe to report Runtime Instance lifecycle or a Diagnostic Flow Record for asynchronous downstream persistence.
_Avoid_: direct diagnostic database write, free-form diagnostic message, Kafka implementation in Swe

**Diagnostic Lease**:
A renewable period during which a Runtime Instance is considered present. Graceful deregistration ends it immediately; expiry makes an abnormally terminated Runtime Instance ineffective.
_Avoid_: permanent active flag, shutdown-only invalidation

**User Question Message ID**:
The stable message identifier for one user-authored question inside a Logical Chat Session. One **User Question Message ID** anchors the answer turn that responds to that question.
_Avoid_: external channel message id, generated UI message id, response id

**Answer Turn**:
The ordered message group anchored by one **User Question Message ID**, including that user question and the messages that follow it until the next user-authored question in the same Logical Chat Session. An **Answer Turn** uses the same chat-history message shape as the full conversation view.
_Avoid_: final answer text, assistant-only bubble, latest response, answer-only slice

**Logical Chat Session**:
The stable conversation identity used to continue chat context across turns. A **Logical Chat Session** is distinct from the persisted chat record used to load or display the conversation.
_Avoid_: chat UUID, UI session row, temporary frontend id

**Chat Record**:
The persisted, displayable record for one conversation, identified by a chat UUID and returned by chat-list APIs. A **Chat Record** is distinct from the **Logical Chat Session** that carries conversational continuity.
_Avoid_: logical chat session, UI session, conversation identity

**Chat Record Last Updated Time**:
The timestamp of the most recent persisted change to a **Chat Record**. It establishes recency when Chat Records are listed.
_Avoid_: Chat Record creation time, message timestamp, Logical Chat Session time

**Conversation Compaction Boundary**:
The durable, user-visible separator within one **Chat Record** marking the point where automatic context compaction or an explicit `/compact` archived earlier messages. It appears immediately through a non-message stream event and is restored from the archive on reload; its archived-message count is the number of display-safe history messages, not rendered cards; it never represents `/new` or `/clear`.
_Avoid_: history-clear marker, new-conversation marker, summary message

**Conversation Compaction Archive**:
The Chat-Record-scoped durable store of messages removed by **Conversation Compaction Boundaries**, with exactly one committed immutable message batch per boundary. Deleting its **Chat Record** permanently deletes this archive, while existing Logical Chat Session state follows its separate retention policy.
_Avoid_: shared daily dialog file, chat transcript, session state

## Flagged Ambiguities

**"Create SubAgent"**:
Resolved to distinguish two cases: starting work creates a **SubAgent Run**, while a Main Agent may also supply a **Run-scoped SubAgent Definition** for that single run. Creating an **Agent-owned Stored SubAgent Definition** occurs only through the expert configuration center.

**"Start Built-in SubAgent By Name"**:
Resolved as ordinary exact-name selection through the compact **SubAgent Start Request**. The Main Agent provides a **SubAgent Name** and objective; a caller-supplied instruction is used only for an unresolved name's Run-scoped Definition.

**"Async SubAgent Creation"**:
Resolved to mean starting a **Background SubAgent Run** that can be queried, completed, or cancelled by run id.

**"SubAgent Subprocess"**:
Resolved as the next **SubAgent Execution Backend** for **Background SubAgent Runs**. It remains an execution mechanism, not a new kind of **SubAgent Definition**.

**"Cancel SubAgent"**:
Resolved for the next stage as **SubAgent Run Cancellation** of the subprocess process group that owns the run. If a terminal result has already been written, cancellation does not overwrite it.

**"Enter Plan Mode"**:
Resolved to require an **Explicit Plan Entry** such as a chat-window toggle or `/plan` command. Automatic silent switching is outside the next stage.

**"Plan Mode Toggle Scope"**:
Resolved as a persistent per-chat-session **Plan Mode State**, stored with the chat metadata rather than treated as a one-shot send option.

**"Plan Mode Permissions"**:
Resolved as a reduced-permission Main Agent mode. SubAgent runtime rules remain available as a separate delegation mechanism, but Plan Mode no longer depends on a default planning SubAgent.

**"Plan Approval"**:
Resolved as the `execute` **Plan Review Decision** on a **Proposed Plan**. `execute` accepts the persisted plan and can transition the chat out of Plan Mode into normal execution.

**"sessionid for Answer Turn lookup"**:
Resolved as the **Logical Chat Session** identifier known to the caller, not the persisted chat record identifier used by the chat history detail endpoint.

**"Answer Turn lookup scope"**:
Resolved as request-identity scoped. A **User Question Message ID** plus **Logical Chat Session** identifies an **Answer Turn** only within the caller's resolved tenant, source, and workspace context.

**"User Question Message ID stream delivery"**:
Resolved as a non-rendering stream notification. Delivering a **User Question Message ID** during chat streaming must not create, mutate, or fail any visible chat response card.

**"User Question Message ID delivery surface"**:
Resolved as an HTTP response header on the chat streaming response, not a renderable stream event.

**"External Answer Turn field names"**:
Resolved as using `msgid` and `sessionid` at the external API boundary while keeping **User Question Message ID** and **Logical Chat Session** as the internal domain terms.

**"User Question Message ID assignment"**:
Resolved as assigning the **User Question Message ID** before chat streaming begins and preserving that same identifier when the user question is stored in conversation memory.

**"Reconnect User Question Message ID"**:
Resolved as no new **User Question Message ID**. A reconnect attaches to an existing stream and must not be treated as a new user question.

**"Answer Turn lookup channel scope"**:
Resolved as Console-only for the current stage. Non-Console channel message identifiers and delivery rules are outside the **Answer Turn** lookup contract.

**"Answer Turn lookup response shape"**:
Resolved as a chat-history response whose `messages` contain the requested **Answer Turn**, including the anchor user question, while `chat` and `status` describe the corresponding chat record.

**"Chat detail User Question Message ID exposure"**:
Resolved as unchanged for the current stage. The full chat detail payload does not gain an additional `msgid` field solely for **Answer Turn** lookup.

**"Answer Turn anchor message shape"**:
Resolved as the same chat-history message shape used by the full conversation view, not a simplified question object.

**"Answer Turn chat record resolution"**:
Resolved as unique under the caller's request identity for **Logical Chat Session**, user, and channel. Any multiple-record handling is legacy-data compatibility, not product semantics.

**"Missing Answer Turn lookup"**:
Resolved as a not-found outcome when the requested **Logical Chat Session** and **User Question Message ID** do not identify a user question in the caller's request-identity scope.

**"Pending Answer Turn lookup"**:
Resolved as a found **Answer Turn** with no non-user messages yet. It returns the anchor user question with the chat's current status instead of a not-found outcome.

**"Non-user Answer Turn anchor"**:
Resolved as not found. An **Answer Turn** lookup only accepts a **User Question Message ID** as its anchor.

**"Execute Mode Transition"**:
Resolved to automatically close the current chat session's **Plan Mode State** before normal execution continues with the persisted Proposed Plan as accepted plan context.

**"Revise Mode Transition"**:
Resolved to keep Plan Mode active and submit the user's revision feedback as a Plan Interaction Response for replanning.

**"Exit Plan Mode Transition"**:
Resolved to automatically close Plan Mode without starting a Main Agent execution run by default, because Plan Mode is itself a special mode of the Main Agent rather than a separate worker.

**"Console Channel Toggle"**:
Resolved to the **Mandatory Console Channel** rule. Channel management may expose Console configuration, but it must not allow the effective Console enablement state to become false.

**"Console Channel vs Terminal Output"**:
Resolved as two different concepts. The always-on rule applies only to the managed **Console Channel** configuration, not to unrelated runtime terminal-output suppression behavior.

**"Plan SubAgent"**:
Resolved as outside the next Plan Mode design. The existing SubAgent runtime and delegation rules remain, but Plan Mode does not require an automatic built-in planning SubAgent.

**"Hook Instrumentation Log"**:
Resolved as a **Hook Telemetry Log Message** emitted for log collection and analysis, not a Trace Span persisted in tracing storage and not a global logging format change.

**"Plan Mode Delegation"**:
Resolved as allowed but optional. Plan Mode may expose readonly **Background SubAgent Tools**, but it does not auto-call `plan-researcher` or any other built-in SubAgent.

**"Plan Mode Tool Scope"**:
Resolved as the **Planning Readonly Policy**: `read_file`, `grep_search`, `glob_search`, `get_current_time`, readonly shell, and readonly **Background SubAgent Tools** are allowed; `write_file`, `edit_file`, `copy_file_to_static`, `update_task_progress`, mutating shell, test commands, deployment commands, and migration commands are forbidden.

**"Plan Interaction Types"**:
Resolved to support only `single_choice`, `multi_choice`, `text`, and `plan_review` in the first version.

**"Plan Card Submission"**:
Resolved as a normal next chat turn carrying **Plan Interaction Response** metadata, not a separate plan-state API call.

**"Planning Clarification Replay"**:
Resolved to not reappear after a page reload or session restore once the card has already been shown in the current chat flow.

**"Planning Clarification Instance"**:
Resolved as assistant-message scoped. A later assistant message that repeats the same clarification content is treated as a new instance and may render again.

**"Planning Clarification Submission Scope"**:
Resolved as assistant-message scoped. Submitting a Planning Clarification Card marks that assistant message's clarification instance as handled, and does not suppress a repeated clarification from a later assistant message.

**"Planning Clarification Display Memory"**:
Resolved as derived from chat history instead of browser storage. A displayed Planning Clarification Card is not hidden merely because it rendered once; it is hidden on restore only after **Planning Clarification Supersession** or a submitted response can be inferred from later chat context.

**"Planning Clarification First Display Timing"**:
Resolved as realtime stream display. A Planning Clarification Card may render as soon as its structured metadata first appears in the active assistant stream, but that displayed instance must not reappear after reload or session restore.

**"Planning Clarification Seen Moment"**:
Replaced by **Planning Clarification Supersession**. First client render alone does not make the clarification seen, resolved, or hidden on restore.

**"Planning Clarification Live Update"**:
Resolved as continuing to update the currently visible Planning Clarification Card while its live assistant response changes. The seen state only prevents replay after reload or session restore; it does not freeze the active card.

**"Dismiss Planning Clarification"**:
Resolved as a **Planning Clarification Dismissal** that closes only the current clarification, restores normal chat input, keeps Plan Mode active, and submits no message.

**"Custom Multi-choice Clarification Response"**:
Resolved as an alternative to all predefined choices. Choosing a custom response clears previously selected predefined choices, and choosing any predefined choice clears the custom response.

**"Plan Card Emission"**:
Resolved as a **Plan Interaction Tool** call. The frontend must not infer planning cards from free-form assistant text JSON.

**"Plan Interaction Tool Shape"**:
Resolved as two built-in tools: `ask_plan_clarification` for clarification cards and `submit_proposed_plan` for final plan review cards.

**"Proposed Plan Fields"**:
Resolved as `plan_id`, `title`, `summary`, `steps[]`, `risks[]`, and `verification[]`. `open_questions[]` and `confidence` are not part of the Proposed Plan protocol or user review card because they do not drive the Plan Review Decision.

**"Scheduled Job Default Model"**:
Resolved as execution-time model resolution: if a **Scheduled Job** has no **Execution Model Slot**, each run uses the current **Tenant Default Model** rather than the default model that existed when the job was created.

**"Scheduled Job Model Override"**:
Resolved as an optional **Execution Model Slot** stored on a **Scheduled Job** only when the user explicitly selects a model for that job.

**"Invalid Scheduled Job Model"**:
Resolved as **Execution Model Fallback**: if a stored **Execution Model Slot** no longer resolves at execution time, the **Scheduled Run** falls back to the current **Tenant Default Model** without a user-facing error while retaining the original slot and fallback reason in logs and execution records.

**"Broadcast Scheduled Job Model"**:
Resolved to copy the **Execution Model Slot** only when the target tenant has the same provider and model. If the target tenant lacks that model, the copied **Scheduled Job** has no **Execution Model Slot**, uses the target tenant's **Tenant Default Model**, and reports a non-failing notice in the broadcast result.

**"Text Scheduled Job Model"**:
Resolved as no **Execution Model Slot**. Text **Scheduled Jobs** do not perform model execution, so any submitted model selection is ignored and the saved job has no **Execution Model Slot**.

**"System Feature Configuration"**:
Resolved as **Source System Configuration** in this context. The configuration is scoped by source, not by tenant or user.

**"Tool Result Compression Switch"**:
Resolved as controlling **Historical Tool Result Compaction** only. **File Read Truncation** needs an independent switch.

**"PostToolUse tool_response"**:
Resolved as **Current Tool Response**: the current tool invocation's business output. It must not mean the full persisted `tool_result` block, the AgentScope `_acting()` return value, or data recovered through **Hook Conversation Snapshot**.

**"Immediate Truncation Configuration Placement"**:
Resolved as sibling configuration under **Source System Configuration**, not nested inside the **Historical Tool Result Compaction** configuration.

**"Tool Exception Contract"**:
Resolved as **Tool Execution Error** for explicit tool-declared failure, with generic exceptions preserved only as a fallback path.

**"Canonical Failed Tool Output Shape"**:
Resolved as **Structured Tool Failure Result**, using the MCP-style `isError=true` result shape rather than plain-text failure strings.

**"Streaming Tool Output Scope"**:
Resolved as **Tool Output Frame** support for long-running tools with naturally incremental textual output. Ordinary one-shot tools should not split their final result into artificial frames.

**"Initial Live Tool Output Scope"**:
Resolved as shell-style terminal tools only. MCP, file-reading, search, browser, and structured business tools do not emit **Tool Output Frames** in the first version.

**"Live Tool Output Limit"**:
Resolved as a presentation and live-replay protection for the **Live Tool Output Area** only. When the final tool result arrives, the tool card's authoritative output follows the normal final-result rules rather than the live-output limit.

**"Live Tool Output Default Limit"**:
Resolved as 64KB or 2000 lines for the **Live Tool Output Area**, whichever is reached first. When the limit is exceeded, Swe keeps the most recent live output and shows an explicit omission marker.

**"Tool Output Frame Stream Shape"**:
Resolved as a dedicated presentation event for **Tool Output Frames**, not a final tool-output message and not a model-visible content delta.

**"Immediate Truncation Defaults"**:
Resolved as preserving existing runtime behavior when a source has no explicit override. File reads keep their current default limit.

**"Disable Immediate Truncation"**:
Resolved as preserving the full immediate output for that output category. It does not mean falling back to an Agent default threshold.

**"Immediate Truncation Limit Name"**:
Resolved as `max_bytes` for immediate truncation concepts. `old_max_bytes` and `recent_max_bytes` remain specific to **Historical Tool Result Compaction**.

**"Immediate Truncation Limit Bounds"**:
Resolved as integer byte limits with a default of 50000 and a minimum of 1000 for **File Read Truncation**. No source-level maximum is defined.

**"File Read Truncation Limit Scope"**:
Resolved as output-only. **File Read Truncation** uses `max_bytes` to limit the text returned to the model and conversation, and does not introduce a source-level limit for how much data is read from storage.

**"File Read Truncation Migration"**:
Resolved as compatibility-first. If a source has no explicit **File Read Truncation** configuration, file reads continue using the historical tool-result recent limit; once **File Read Truncation** is explicitly configured, it fully owns file-read immediate truncation.

**"File Read Truncation Safety Limit"**:
Resolved as no separate non-configurable hard limit for file-read immediate output. When file-read truncation is explicitly disabled, Swe should not silently impose another truncation threshold for that category.

**"File Read Internal Protection"**:
Resolved as outside **Source System Configuration**. Swe may keep an internal storage-read protection limit, but hitting it must be visible rather than silently treated as a complete file read.

**"Tool Output Controls UI"**:
Resolved as one user-facing group with two sections: **Historical Tool Result Compaction** and **File Read Truncation**.

**"Immediate Truncation Explicit Ownership"**:
Resolved as represented by retaining the immediate truncation configuration object, at least with its `enabled` field. Default-value pruning must not erase explicit ownership of **File Read Truncation**.

**"Cron Entry"**:
Resolved as **Scheduled Run Boundary** when discussing runtime behavior. Cron management API requests remain normal HTTP requests and are outside this term.

**"Skill Reload During A Session"**:
Resolved as **Session Skill Freshness** with next-turn scope. A skill file change must affect the next turn in the same chat session, not the currently running turn.

**"Skill Update Scope"**:
Resolved as **Skill Directory Revision**, not `SKILL.md`-only monitoring. Any tracked file change inside the skill directory counts as a skill update.

**"Skill Freshness Comparison"**:
Resolved as comparing **Skill Directory Freshness Token** values for this feature, not recomputing strict **Skill Directory Revision** values on every turn.

**"Skill Freshness Token Scope"**:
Resolved as a stable digest of each tracked file's relative path, `mtime_ns`, and size across the skill directory tree, not just the root directory and `SKILL.md`.

**"Associated Skills To Monitor"**:
Resolved as the session's **Session Associated Skill Set** only. Skills that the session never associated with are outside the monitoring scope.

**"Associated Skill Persistence"**:
Resolved as persisting a **Session Skill Snapshot** in session state, not reconstructing it from tracing or other runtime records.

**"Skill Update Handling"**:
Resolved as **Skill Freshness Refresh** plus a model-only **Skill Freshness Notice**. The notice is visible to the model for one turn, but is not exposed to the Console stream or persisted into chat history.

**"When A Skill Becomes Associated"**:
Resolved as **Confirmed Skill Association** only. Low-confidence inference without actual activation must not expand the **Session Associated Skill Set**.

**"Associated Skill Disappeared"**:
Resolved as **Missing Associated Skill** with ignore semantics. If an associated skill no longer exists at next-turn freshness check time, Swe continues the turn, treats that absence as no effective skill change for the first version, and silently removes the stale snapshot entry.

**"When To Update The Session Skill Snapshot"**:
Resolved as writing an **Applied Skill Snapshot** immediately after freshness detection and notice injection for the current turn, rather than waiting for turn completion.

**"Where The Session Skill Snapshot Lives"**:
Resolved as a top-level **Session Skill Snapshot Record** in session state, parallel to `hook_overlay`, not nested under `agent`.

**"What A Session Skill Snapshot Entry Stores"**:
Resolved as at least `skill_name`, `resolved_skill_dir`, and `freshness_token`, not just the skill name alone.

**"When To Persist A Newly Associated Skill"**:
Resolved as **Immediate Skill Snapshot Capture**. A newly confirmed associated skill must be written to the top-level session snapshot immediately in the same turn.

**"Associated Skill Directory Changed"**:
Resolved as **Associated Skill Directory Switch**. If a session-associated skill name resolves to a different directory on a later turn, Swe must treat that as a real change, trigger refresh/notice, and overwrite the stored snapshot entry.

**"Associated Skill Lost Enabled/Effective Status"**:
Resolved as **Associated Skill Withdrawal**. If a session-associated skill is no longer effective for the current turn, Swe must treat that as a real change, trigger refresh/notice, and remove the stored snapshot entry.

**"Multiple Skill Changes In One Turn"**:
Resolved as a single **Aggregated Skill Freshness Notice** that lists each affected skill and its change type within the same turn.

**"Immediate Truncation Raw Configuration Display"**:
Resolved as exposing absence for **File Read Truncation** as inheriting the historical recent tool-result limit until independently configured.

**"Tool Output Controls Scope"**:
Resolved as limited to the Source System Configuration page and runtime resolution for current user-facing controls. The Agent configuration page no longer exposes historical tool-result compaction controls, while existing Agent runtime configuration remains available as inherited baseline behavior.

**"Current Session Context Usage"**:
Resolved as **Persisted Context Occupancy**, meaning the estimated persisted session context divided by the configured **Context Window**. It excludes the current unsent composer text and does not mean cumulative token usage across completed calls.

**"Context Window Capacity"**:
Resolved as the Main Agent running configuration `max_input_length`, not provider-reported model metadata. The indicator follows Swe's runtime budget because compaction and fit checks are governed by that configuration.

**"System Self-Check"**:
Resolved as **System Runtime Diagnostic**. The existing lightweight health endpoint remains a liveness probe, while the scheduled `HEARTBEAT.md` run remains an Agent Heartbeat.

**"Health Endpoint"**:
Resolved as **Liveness Probe** when referring to `/api/health/health`. It is not a readiness check and does not report dependency availability.

**"output_len=0"**:
Resolved as **Empty Model Output** only when discussing a successful model call that returns no usable assistant content. Scheduled Run or stream-level `output_len=0` remains an execution symptom and must not be treated as the canonical model-call concept.

**"Thinking-Only Model Output"**:
Resolved as not being **Empty Model Output**. Reasoning content is usable model content even when no user-visible final text is present.

**"Empty Model Output Retry Count"**:
Resolved as a fixed single retry for each model call. This retry is independent from normal transient-error LLM retry settings and still applies when normal LLM retry is disabled.

**"Streaming Empty Model Output"**:
Resolved at the whole-stream boundary. An individual empty stream chunk does not trigger an **Empty Model Output** retry; a completed stream that produced no usable model content triggers one full model-call retry.

**"Exhausted Empty Model Output Retry"**:
Resolved as an explicit model-call failure. If the fixed single retry also returns **Empty Model Output**, Swe raises a diagnostic error instead of treating the call as successfully completed.

**"Flask Worker Usage"**:
Resolved as **Request Execution Load**. Swe does not run Flask or a multi-worker web-server pool; the diagnostic reports the load and responsiveness of the single-worker Uvicorn/FastAPI backend instead of tenant-level workload statistics or Supervisor process state.

**"Diagnostic Instance"**:
Resolved as a **Runtime Instance**, meaning one running Swe service container. It is distinct from the business-facing instance records used for user allocation.

**"Logging System"**:
Resolved as the **Application Log Output Pipeline** when discussing asynchronous logging output. It does not mean changing **Hook Telemetry Log Message** schema, business operation logs, tracing storage, or **Tool Output Frames**.

**Context Reference**:
A user-selected runtime resource in a chat message. A Context Reference has one type—Skill, MCP Tool, or Workspace File—and is translated into that type's own trusted instruction context for the current turn.
_Avoid_: plain @ text, forced tool invocation, file upload

**Workspace File Context Reference**:
A Context Reference for a file owned by the current workspace, scoped to either its `media` directory or its `static` directory. It identifies an existing runtime file; it is not a new uploaded attachment.
_Avoid_: arbitrary local file, public file, chat upload

**Chat File Manager**:
The tenant-scoped browser for files in the current Agent workspace. It presents five controlled root directories and never exposes arbitrary host filesystem paths.
_Avoid_: file preview drawer, host file browser, general file storage

**Working Directory**:
The root path of the current tenant's Agent workspace. It is the default root shown when the **Chat File Manager** opens.
_Avoid_: global workspace, source checkout, host home directory

**File Manager Hidden Managed Directories**:
The two tenant-workspace directories omitted from the Working Directory view: `sessions`, which is reached through the read-only Conversation Directory, and `governance`, which is reached only through the controlled File Manager Recycle Bin. All other workspace files and directories remain visible in the Working Directory.
_Avoid_: hidden workspace policy, governance root browser, sessions bypass

**Upload Directory**:
The `media` root within the current tenant's Agent workspace, containing files uploaded through chat.
_Avoid_: attachment list, arbitrary upload location

**Download Directory**:
The `static` root within the current tenant's Agent workspace, containing files made available for download or generated for the user.
_Avoid_: browser download history, client download folder

**File Manager Recycle Bin**:
The controlled file-manager view of the current tenant's governance archive. It presents archived files by their original file identity and permits only supported restore or permanent-delete operations; it is not a browser for the `governance` root or its control records.
_Avoid_: governance directory browser, raw archive files, ordinary directory

**File Manager Restore Conflict**:
The outcome when a File Manager Recycle Bin item cannot return to its original path because a file already exists there. Restore does not overwrite the existing file and leaves the archive item available until the user resolves the conflict.
_Avoid_: overwrite-on-restore, automatic rename, lost archive item

**File Manager Permanent Deletion Confirmation**:
The explicit, irreversible confirmation required before permanently deleting a File Manager Recycle Bin item. It displays the file's original path, uses a dangerous-action affordance, and provides no undo after confirmation.
_Avoid_: one-click permanent delete, generic confirmation, undoable purge

**File Manager Entry Date**:
The weak secondary date shown for one file-manager row. Ordinary directories show the file's modification time, while the File Manager Recycle Bin shows the time the file entered the archive.
_Avoid_: file size metadata, one date meaning for every root, recycle-bin modification time

**File Manager Directory Incremental Loading**:
The independent waterfall-style loading behavior for each directory column. It loads the first 100 stable-order entries and loads later pages as the user approaches that column's bottom; Current Directory Search uses the same server-side paging behavior.
_Avoid_: one global scroll, capped flat workspace list, client-only large-directory filtering

**File Manager Symbolic Link Boundary**:
The safety rule for a symbolic link encountered in a visible workspace directory. The file manager displays it as restricted but never resolves, follows, previews, edits, downloads, deletes, or uses it as an upload destination.
_Avoid_: workspace-escaping link traversal, hidden symlink, supported symlink file operation

**File Manager HTML Preview Sandbox**:
The isolated frame used to preview an HTML file. It permits scripts to execute but withholds same-origin access, top-level navigation, popups, and downloads from the embedded document.
_Avoid_: trusted HTML preview, same-origin embedded file, unrestricted preview frame

**File Manager Breadcrumb Root**:
The first clickable segment of a file-manager breadcrumb: the active shortcut directory. It returns to that root and replaces the non-navigable `Home` label.
_Avoid_: synthetic Home breadcrumb, host filesystem root, inactive shortcut root

**File Manager Breadcrumb Reanchor**:
The navigation behavior after a user selects any file-manager breadcrumb segment. Its directory becomes the left-column starting point, its default path repopulates the following columns, and the previously visible path and file preview are cleared.
_Avoid_: partial breadcrumb rewind, preserved stale preview, in-place ancestor jump

**File Manager Directory Capability**:
The permitted user operations for a **Chat File Manager** root. Working, Upload, and Download Directories permit browsing, upload, editing, downloading, and recoverable deletion; the Conversation Directory permits browsing, previewing, and downloading only; the **File Manager Recycle Bin** permits restoring or permanently deleting archived files only.
_Avoid_: uniform directory permissions, session-file editing, recycle-bin upload

**File Manager Initial Column State**:
The state after the **Chat File Manager** enters a root directory. The root's items occupy the left column, its default first folder becomes the middle directory, and that folder's default first child folder becomes the right directory; each column lists the direct contents of its directory.
_Avoid_: synthetic Home column, selection-empty initial state, inaccessible parent layer

**File Manager Default Directory Order**:
The stable order used by the **Chat File Manager** to display directory entries and choose each default folder for the initial path. Folders precede files, and entries within each kind use case-insensitive natural name order.
_Avoid_: modification-time default order, filesystem enumeration order, files-first default path

**File Manager Default Path Termination**:
The rule when initial automatic traversal reaches a directory without a child folder before all three columns are populated. Traversal stops, the remaining columns identify the absent child-folder level, and no file is selected or previewed automatically.
_Avoid_: auto-previewed first file, fabricated directory level, file-based auto traversal

**File Manager Current Directory Search**:
The non-recursive, case-insensitive filename filter for the direct child entries of the directory represented by the middle column. It does not change the selected item or path; when no middle directory exists, it instead filters the current shortcut-root directory.
_Avoid_: workspace-wide search, recursive search, search-driven navigation

**File Manager Column Advance**:
The selection rule for the three-column browser. Selecting a folder in a non-rightmost column displays its direct children in the next column without moving the window. Selecting either a folder or a file in the rightmost column moves the three-column window one level left.
_Avoid_: double-click-to-enter, manual navigation confirmation, fixed parent-current-preview columns

**File Manager File Advance Result**:
The newly exposed rightmost column after a file triggers a **File Manager Column Advance**. It presents that file's preview or details in place, including its applicable editing action, rather than opening a separate preview overlay or leaving the column empty.
_Avoid_: nested preview modal, empty trailing column, detached file inspector

**File Manager Editable Text File**:
A file whose content is safely classified as plain UTF-8 text, including text, Markdown, and HTML files. It supports in-place editing in the **Chat File Manager**; binary, Office, PDF, image, audio, and video files do not.
_Avoid_: universal file editor, Office editing, binary-text coercion

**File Manager Large Text Preview**:
The bounded text-file reading rule. A text file of at most 1 MB is read in full and is eligible for editing; a larger text file previews only its first 1 MB, remains downloadable, and is not editable.
_Avoid_: character-count truncation, unbounded text read, large-text editing

**File Manager Save Conflict**:
The outcome when a **File Manager Editable Text File** has changed after its editor loaded it but before the user saves. The save is rejected without overwriting the current file, and the user's unsaved draft remains available for comparison or resolution.
_Avoid_: last-writer-wins save, silent overwrite, discarded draft

**File Manager Unsaved-Edit Guard**:
The confirmation required before closing the file manager or taking a navigation action that would replace an unsaved text-editor draft. The user may save, discard the draft, or cancel the pending action; the action proceeds after a successful save or an explicit discard only.
_Avoid_: implicit draft discard, navigation-first save, silent editor reset

**File Manager Recoverable Deletion**:
The file-only deletion operation that moves one file from a mutable **Chat File Manager** directory into the **File Manager Recycle Bin**. Directories cannot be deleted through the first file-manager release.
_Avoid_: recursive directory deletion, permanent ordinary-directory delete, file-system-wide trash

**File Manager Upload Availability**:
The Upload action is unavailable in the Conversation Directory and the File Manager Recycle Bin, with an explanation of that restriction. A successful upload refreshes its destination directory without selecting the new file automatically.
_Avoid_: session upload, recycle-bin upload, upload-driven file selection

**File Manager Upload Name Conflict**:
The outcome when an upload's filename already exists in its destination directory. The upload is rejected without overwriting or automatically renaming either file; the user must rename the local file and retry.
_Avoid_: overwrite upload, auto-suffixed upload, silent replacement

**File Manager Mutation Audit Record**:
The application-audit record for a file-manager upload, save, recoverable deletion, restore, or permanent deletion. It identifies the actor, time, operation, path, and result without retaining file contents; previews and downloads create no such record.
_Avoid_: file-content audit, unlogged workspace mutation, preview analytics

**File Manager File Download**:
The detail-panel action that downloads one selected file from the Working, Upload, Download, or Conversation Directory. It is unavailable in the File Manager Recycle Bin and does not create archive downloads for folders.
_Avoid_: directory ZIP download, recycle-bin download, list-row bulk download

**Conversation Directory**:
The `sessions` root within the current tenant's Agent workspace, containing conversation-scoped files.
_Avoid_: chat transcript, current browser session, global sessions directory

**On-Demand File Reference Instruction**:
The trusted instruction context created from a Workspace File Context Reference after the backend re-resolves and validates it within the current workspace. It tells the Main Agent that the file is user-selected and may be read or analyzed on demand, without inlining its contents or binary data.
_Avoid_: automatic file attachment, inline file content, unvalidated file path

**Context Reference Search**:
The non-empty query after `@` that searches the current Agent's Skills, Callable MCP Tools, and Workspace File Context References. Skills and MCP Tools retain their default presence when the query is empty; files are searched only after the user supplies a query.
_Avoid_: eager workspace file enumeration, empty-query file listing

**Context Reference Turn Scope**:
The lifecycle shared by all Context References: their typed instruction contexts apply only to the next submitted user message and are cleared immediately after that request is created. They do not persist implicitly across later conversation turns.
_Avoid_: persistent mention, conversation-scoped reference, sticky tool selection

**Context Reference Selection Set**:
The unique set of Context References chosen for one request. It deduplicates repeated choices by stable type-specific identity while allowing same-named resources of different types to coexist.
_Avoid_: duplicate mention list, name-only deduplication, persistent selection

**Context Reference Token**:
The non-editable, type-icon-bearing inline representation of a selected Context Reference in the message editor. Skills display `@skill`, MCP Tools display `@server/tool`, and Workspace Files display `@filename` with the root-prefixed path available as supplementary text; token deletion changes the structured selection set.
_Avoid_: editable reference text, text-parsed selection, untyped mention token

**Context Reference Discovery Hint**:
The footer message shown only while the user has typed `@` without a search term. It tells the user that further input searches tools and files; a non-empty query replaces it with results or an empty-result state.
_Avoid_: persistent search footer, query-time instruction

**Context Reference Result Group**:
A typed category shown in the mention overlay only when it has one or more matching Context References. Empty categories are omitted rather than rendered as empty sections.
_Avoid_: empty category section, category-level no-results row

**Context Reference Result Group Order**:
The fixed mention-overlay order for non-empty result groups: Skills, then MCP Tools, then Files.
_Avoid_: relevance-shuffled groups, files-first grouping

**Context Reference Empty Result State**:
The single mention-overlay state displayed when a non-empty Context Reference Search finds no Skills, Callable MCP Tools, or Workspace File Context References. It replaces all result groups.
_Avoid_: per-category empty states, blank search overlay

**Workspace File Search Result**:
A filename-matched Workspace File Context Reference from either the `media` or `static` directory. Both directories appear together in the single Files group, with no separate source grouping; each result category is limited to four items.
_Avoid_: media group, static group, path-content search

**Workspace File Result Path Label**:
The secondary display text for a Workspace File Search Result. It uses the source-root-prefixed relative path, such as `media/image.png` or `static/reports/summary.pdf`, to distinguish same-named files while keeping them in one Files group.
_Avoid_: filename-only file selection, separate source group

**Callable MCP Tool**:
An MCP Tool that is enabled for the current Agent and was successfully discovered for the current Context Reference lookup. A failed MCP service contributes no tool or error placeholder to the mention overlay.
_Avoid_: configured MCP tool, unavailable MCP tool, failed-server row

**MCP Tool Result Identity**:
The stable identity and primary label for a Callable MCP Tool in the mention overlay: its MCP server identifier paired with its tool name. The UI presents it as `server / tool` and uses the tool description as secondary text.
_Avoid_: tool-name-only identity, ambiguous MCP tool label

**Preferred MCP Tool Instruction**:
The typed instruction context for a selected Callable MCP Tool. It tells the Main Agent to prefer that tool when appropriate for the current request, but does not require a call or grant access beyond the tool's existing runtime availability.
_Avoid_: forced MCP invocation, tool authorization grant, automatic tool call

**Context Reference Directory Cache**:
The process-local in-memory cache of Context Reference discovery snapshots and filename indexes. It is keyed by effective tenant and Agent identity, stores no file contents, and is never shared across processes or workspace scopes.
_Avoid_: global reference cache, cross-tenant cache, file-content cache

**Context Reference Cache Freshness**:
The per-resource maximum age for a Context Reference Directory Cache snapshot, measured with a monotonic clock: five minutes for Skills and three minutes for Callable MCP Tools and the merged Workspace File filename index.
_Avoid_: one shared TTL, wall-clock expiry, indefinite discovery cache

**Context Reference Cache Hard Expiry**:
The cache-failure policy that discards an expired discovery snapshot rather than serving it when refresh fails. The failed category contributes no results, and each selected reference is independently revalidated before instruction context is created.
_Avoid_: stale-on-error reference list, unverified selected reference, stale MCP fallback

**Context Reference Cache Invalidation**:
The first-release cache invalidation policy: snapshots expire only through their configured TTLs. Configuration updates, uploads, and filesystem changes do not evict Context Reference Directory Cache entries early.
_Avoid_: mutation-triggered cache eviction, filesystem watcher invalidation, instant discovery refresh

**Context Reference Cache Admission and Capacity**:
A Context Reference Directory Cache entry is created lazily only when a user opens the mention overlay with `@`. The cache holds at most 128 tenant-and-Agent-scoped entries, removes expired entries during cache access, and evicts the least recently used entry when full.
_Avoid_: eager startup cache warming, unbounded reference cache, FIFO eviction

**Context Reference Cache Single-Flight Refresh**:
The refresh rule that permits one in-progress discovery refresh for each tenant-and-Agent scope and resource category. Concurrent cache misses wait for that refresh and consume its shared success result or shared empty failure result.
_Avoid_: cache stampede, duplicate MCP discovery, parallel directory scans

**Context Reference Cache TTL Configuration**:
The first-release decision that Context Reference Cache Freshness values are fixed backend constants, not a source-system setting, environment override, or public API configuration surface.
_Avoid_: runtime TTL tuning, cache settings UI, per-tenant cache TTL

**Context Reference MCP Discovery Budget**:
The bounded discovery window used when refreshing Callable MCP Tools: each MCP service has two seconds to respond, all services discover in parallel, and the overall overlay request waits at most three seconds. Only services that succeed within the budget contribute tools; timeout is silent.
_Avoid_: unbounded MCP discovery, serial MCP lookup, timeout error row

**Workspace File Index Capacity**:
The maximum number of files retained in each source-root portion of a Workspace File filename index. `media` and `static` each retain at most 5,000 files, selecting the most recently modified files when their directory has more.
_Avoid_: unbounded directory index, whole-directory search at request time, source-combined capacity limit

## Stop Hook Language

**Stop Hook**:
The single completion lifecycle event for every candidate Assistant Response. Each configured handler runs once and may perform its own attempt-recording or notification work. Its merged decision approves or blocks completion.
_Avoid_: BeforeStop hook, observation-only stop hook

**Stop Decision**:
The only valid completion decision from a Stop Hook: `allow` approves the candidate Assistant Response and `block` rejects that completion attempt. An explicit `block` may schedule a bounded automatic follow-up Agent turn; if any matched handler blocks, the merged decision blocks.
_Avoid_: deny, stop, implicit retry

**Stop Handler Failure**:
An execution failure from a Stop Hook handler. With `failPolicy: block`, it ends the request as incomplete with the failure reason and never schedules an automatic follow-up; with `failPolicy: allow`, it is diagnostic only. Only an explicit Stop Decision of `block` may request another Agent turn.
_Avoid_: retryable hook failure, silent completion failure

**Stop Migration**:
The non-compatible removal of the `BeforeStop` event. Configuration must use `Stop`; a residual `BeforeStop` configuration is invalid rather than silently translated.
_Avoid_: BeforeStop compatibility alias, automatic event translation

**Stop Trigger**:
The boundary at which a normal candidate Assistant Response is about to complete a request. Tool-hook terminal-stop paths and turns without a candidate Assistant Response skip Stop.
_Avoid_: tool termination audit, no-output completion hook

## Example Dialogue

Developer: "When Plan Mode starts, should we create a SubAgent?"

Domain Expert: "No. Plan Mode does not create a SubAgent by default; it is a special mode of the Main Agent. The Main Agent may still choose Plan Delegation explicitly when readonly delegation is available."

Developer: "Can the Main Agent decide to use Plan Mode by itself?"

Domain Expert: "It can suggest Plan Mode later, but this stage only enters Plan Mode after an Explicit Plan Entry."

Developer: "If the user enables the Plan Mode toggle, does it affect only the next message?"

Domain Expert: "No. It persists as the current Plan Mode State for that chat session until the user turns it off."

Developer: "Does Plan Mode freeze all writes until the user executes a plan?"

Domain Expert: "Yes. In Plan Mode, the Main Agent itself is permission-limited until planning is completed."

Developer: "Does executing a plan unlock write tools?"

Domain Expert: "`execute` accepts the persisted Proposed Plan and can move the chat back to normal execution, where the Main Agent regains its normal permissions."

Developer: "Is the hook attached to a SubAgent Definition or to an Agent Profile?"

Domain Expert: "It is an Agent Profile Hook. Its script belongs to that Agent Profile and is not a shared Skill asset."

Developer: "Can a tenant administrator replace the source's `read_file` implementation?"

Domain Expert: "No. Only a Source Tool Administrator may publish a Source Built-in Tool. An Override keeps `read_file`'s complete tool Schema, runs through the normal safety boundaries, and still respects each Agent's enabled or disabled choice."

Developer: "Will a new source tool appear only when the model asks for it?"

Domain Expert: "No. Every source-enabled tool that the Agent has not disabled is part of the Agent run's catalog from the start of that run."

Developer: "Can the `reviewer` agent in the security Skill collide with a `reviewer` in the Python Skill?"

Domain Expert: "No. The runtime exposes them as `security:reviewer` and `python:reviewer`; each qualified name belongs only to its Skill."

Developer: "Does every enabled Skill become available to `security:reviewer`?"

Domain Expert: "No. It receives only Skills and MCP clients named in its Definition Package. Missing or disabled dependencies are silently omitted."

Developer: "May the reviewer edit a file?"

Domain Expert: "Only when its inherited built-in tool set remains permitted by its allow/deny settings and by the parent Agent's Tool Guard and approval policy. A background run never waits for a new approval."
