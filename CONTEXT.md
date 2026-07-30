# Swe Agent Runtime

This context defines the domain language for Swe's agent orchestration runtime, especially how the main agent coordinates SubAgent work.

## Language

**SubAgent Definition**:
A named, versioned worker profile that describes what kind of delegated work a SubAgent can perform. One **SubAgent Definition** can be used by many **SubAgent Runs**.
_Avoid_: custom subagent, subagent template, agent config

**SubAgent Run**:
A single observable execution instance created when the main agent delegates work to a SubAgent Definition. A **SubAgent Run** is not a new SubAgent Definition.
_Avoid_: create subagent, custom subagent, subagent profile

**Delegation Run**:
Alias for **SubAgent Run** when emphasizing the parent-to-worker handoff rather than the worker identity.
_Avoid_: subagent creation

**Main Agent**:
The user-facing agent that owns global task understanding, user interaction, mode decisions, and final responses.
_Avoid_: parent bot, orchestrator bot

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
A planning artifact presented by the Main Agent for user review before continuing work. A Proposed Plan contains a plan id, title, summary, steps, risks, verification items, open questions, and confidence.
_Avoid_: permission request, execution unlock

**Plan Review Decision**:
The user's response to a Proposed Plan: `revise`, `execute`, or `exit_plan`. `revise` keeps Plan Mode active for replanning, `execute` accepts the persisted Proposed Plan and continues in normal mode, and `exit_plan` closes Plan Mode without starting a Main Agent execution run by default.
_Avoid_: tool approval, permission grant

**Plan Interaction Card**:
A structured chat UI card used by the Main Agent to ask for planning clarification or present a Proposed Plan. A Plan Interaction Card is user-facing and is not emitted directly by a SubAgent.
_Avoid_: subagent question card, free-form prompt hack

**Planning Clarification Card**:
A Plan Interaction Card that asks the user for missing planning information using single choice, multiple choice, or text input.
_Avoid_: generic form, survey

**Plan Interaction Response**:
The user's structured answer to a Plan Interaction Card, submitted as the next normal chat turn with metadata that identifies the card and selected or entered value.
_Avoid_: hidden plan API update, out-of-band form submission

**Plan Interaction Tool**:
A built-in Main Agent tool that emits Plan Interaction Cards through validated structured metadata.
_Avoid_: markdown JSON card, frontend text parser

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
An executable custom tool asset owned by one source and available to every tenant under that source. It is distinct from an Agent Profile tool configuration; tenants may use it but cannot alter its source-owned script or lifecycle.
_Avoid_: tenant tool script, source configuration JSON, Agent-owned shared tool

**Source Tool Library**:
The source-scoped management collection of Source Built-in Tools on the System Configuration page. It has independent source-owned storage and lifecycle, supports complete-file upload rather than browser editing, and is not Marketplace or tenant-workspace storage.
_Avoid_: source configuration JSON, agent tool page, browser script editor

**Source Built-in Tool Draft**:
An unpublished source-tool version that has passed static validation and the mandatory blocking safety gate. A Source Tool Administrator may explicitly test, discard, or publish it; it does not alter any Agent catalog before publication.
_Avoid_: implicit publication, unscanned source tool, active source tool

**Source Built-in Tool Override**:
The source-level precedence rule under which a Source Built-in Tool replaces a Swe code-defined built-in while preserving its complete tool JSON Schema. It never overrides Skill or MCP tools and cannot bypass an Agent's disabled choice.
_Avoid_: registration-order override, Schema-changing override, Skill override, MCP override

**Source Built-in Tool Activation Boundary**:
The start of an Agent run, when it snapshots its effective Source Built-in Tool catalog. Publication, replacement, and deactivation affect only later Agent runs; a running Agent retains its starting catalog.
_Avoid_: mid-run tool mutation, retroactive catalogue change

**Source System Configuration Override**:
A value explicitly saved in **Source System Configuration** that replaces the corresponding broader runtime setting for requests from that source. Missing values are inheritance, not implicit overrides.
_Avoid_: source default, tenant override, page default

**Runtime Request Identity**:
The tenant and source context that determines which runtime configuration and model selection a request observes. One **Runtime Request Identity** resolves to one **Tenant Provider Configuration** view for provider and active-model reads.
_Avoid_: cache key, auth header set, iframe context

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
The runtime-detected participation of a skill in a turn, established by tool or asset evidence. It is distinct from **User-Selected Skill** and is the only basis for tool-call skill attribution.
_Avoid_: selected skill, requested skill, assumed skill invocation

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
A `PreToolUse` hook outcome with the explicitly returned `stop` decision, expressed as `{"decision":"stop","reason":"…"}` and available to every handler type, that rejects the pending tool invocation and ends the current Main Agent turn without another model call. The first `stop` in handler order is authoritative and cannot be replaced by another decision or input update; handler failures and `failPolicy:block` never imply it. Its reason, or the stable fallback `Hook requested stop`, is always emitted and persisted as the turn's final assistant message while the failed tool result remains available for tool presentation and audit as `hook_stopped`. It blocks unstarted peer calls and requests best-effort cancellation of already-started peer calls; it does not promise rollback of external side effects. It bypasses later `BeforeStop` and `Stop` hooks. It is distinct from `deny` and `block`, which reject the invocation but allow the Main Agent to choose a different next action.
_Avoid_: terminal deny, blocked tool, cancelled session

**PostTool Terminal Stop**:
A `PostToolUse` or `PostToolUseFailure` hook outcome with the explicitly returned `stop` decision, expressed as `{"decision":"stop","reason":"…"}`, that ends the current Main Agent turn after the tool outcome is known. It requests best-effort cancellation of unfinished peer calls while retaining completed outcomes and without promising external rollback. It records the completed tool outcome and post-hook context before the final assistant reason, then bypasses `BeforeStop` and `Stop` hooks. It does not rewrite the completed tool outcome; for a failed tool, it replaces propagation of the original tool exception while retaining that failure for presentation and audit. Hook failure, `failPolicy:block`, `deny`, and `block` never imply it. It is distinct from `deny` and `block`, which remain non-terminal for post-tool events.
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

## Flagged Ambiguities

**"Create SubAgent"**:
Resolved to mean creating a **SubAgent Run**, not creating a new **SubAgent Definition**. User-defined SubAgent Definition CRUD/UI is outside the next stage.

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
Resolved as allowed but optional. Plan Mode may expose `delegate_to_subagent`, but it does not auto-call `plan-researcher` or any other built-in SubAgent.

**"Plan Mode Tool Scope"**:
Resolved as the **Planning Readonly Policy**: `read_file`, `grep_search`, `glob_search`, `get_current_time`, readonly shell, and readonly `delegate_to_subagent` are allowed; `write_file`, `edit_file`, `copy_file_to_static`, `update_task_progress`, mutating shell, test commands, deployment commands, and migration commands are forbidden.

**"Plan Interaction Types"**:
Resolved to support only `single_choice`, `multi_choice`, `text_input`, and `plan_review` in the first version.

**"Plan Card Submission"**:
Resolved as a normal next chat turn carrying **Plan Interaction Response** metadata, not a separate plan-state API call.

**"Plan Card Emission"**:
Resolved as a **Plan Interaction Tool** call. The frontend must not infer planning cards from free-form assistant text JSON.

**"Plan Interaction Tool Shape"**:
Resolved as two built-in tools: `ask_plan_clarification` for clarification cards and `submit_proposed_plan` for final plan review cards.

**"Proposed Plan Fields"**:
Resolved as `plan_id`, `title`, `summary`, `steps[]`, `risks[]`, `verification[]`, `open_questions[]`, and `confidence` for the first version.

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
