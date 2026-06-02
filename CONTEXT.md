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

**Scheduled Run**:
A single execution of a **Scheduled Job**, whether triggered by schedule or manually.
_Avoid_: cron call, job instance

**Scheduled Run Boundary**:
A runtime boundary that starts scheduled work outside an incoming user HTTP request. It includes **Scheduled Job**, heartbeat, and dream execution, but not cron management API requests.
_Avoid_: cron entry, cron API, scheduler callback

**Execution Model Slot**:
An optional model selection pinned to a **Scheduled Job**. If absent, each **Scheduled Run** uses the **Tenant Default Model** at execution time.
_Avoid_: model params, cron model

**Execution Model Fallback**:
The behavior where a **Scheduled Run** uses the current **Tenant Default Model** when its configured **Execution Model Slot** cannot be used. The fallback is silent in the user interface but must remain visible in operational records.
_Avoid_: hard failure, invisible fallback

**Tenant Default Model**:
The active LLM selection for a tenant, used by agent work when no narrower **Execution Model Slot** is specified.
_Avoid_: global model, system default model

**Source System Configuration**:
A source-scoped runtime configuration surface for behavior shared by requests from the same external source. It is not a tenant configuration and does not describe user, organization, or workspace identity.
_Avoid_: system feature configuration, tenant config, user config

**Historical Tool Result Compaction**:
A conversation-history cleanup behavior that shortens previously stored tool results so the Main Agent can continue within context limits. It is separate from truncating the first result returned by a tool call.
_Avoid_: tool output truncation, file read truncation, live tool truncation

**File Read Truncation**:
A source-scoped limit on text returned by file-reading tools during the same turn that reads the file. It is separate from **Historical Tool Result Compaction**.
_Avoid_: file compaction, historical tool result compaction

**Tool Output Controls**:
The user-facing grouping for source-scoped controls over historical tool-result compaction and file-read output truncation.
_Avoid_: tool result compression configuration

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

**"Execute Mode Transition"**:
Resolved to automatically close the current chat session's **Plan Mode State** before normal execution continues with the persisted Proposed Plan as accepted plan context.

**"Revise Mode Transition"**:
Resolved to keep Plan Mode active and submit the user's revision feedback as a Plan Interaction Response for replanning.

**"Exit Plan Mode Transition"**:
Resolved to automatically close Plan Mode without starting a Main Agent execution run by default, because Plan Mode is itself a special mode of the Main Agent rather than a separate worker.

**"Plan SubAgent"**:
Resolved as outside the next Plan Mode design. The existing SubAgent runtime and delegation rules remain, but Plan Mode does not require an automatic built-in planning SubAgent.

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

**"Immediate Truncation Configuration Placement"**:
Resolved as sibling configuration under **Source System Configuration**, not nested inside the **Historical Tool Result Compaction** configuration.

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

**"Immediate Truncation Raw Configuration Display"**:
Resolved as exposing absence for **File Read Truncation** as inheriting the historical recent tool-result limit until independently configured.

**"Tool Output Controls Scope"**:
Resolved as limited to the Source System Configuration page and runtime resolution for this change. The Agent configuration page keeps the existing historical tool-result compaction controls for now.

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
