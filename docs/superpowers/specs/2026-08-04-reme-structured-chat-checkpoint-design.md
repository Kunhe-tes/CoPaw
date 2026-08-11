# ReMe Structured Chat Checkpoint Design

**Status:** Approved design — pending implementation planning
**Date:** 2026-08-04

## Purpose

Replace the current ReMe compacted-summary-as-state approach with a Chat-scoped, recoverable checkpoint protocol. The protocol must retain current task continuity near the context limit without losing user constraints, unfinished work, failures, tool transactions, or recoverable evidence.

This design complements the existing unified tool-result output-budget and recoverable-reference protocol. It does not introduce another tool-output truncation configuration.

## Current behavior and gap

The current pre-reasoning hook counts system prompt plus `compressed_summary`, asks ReMe to select old messages after one threshold is reached, and stores the returned Markdown as the next `compressed_summary`. Uncompressed messages remain online; compacted messages are archived by Chat. ReMe's Markdown format contains Goal, Constraints & Preferences, Progress, Key Decisions, Next Steps, and Critical Context.

The current Markdown is both the stored state and the model input. It is only minimally validated, can be repeatedly summarized, and has no Agent-facing, Chat-scoped retrieval path for archived conversation evidence.

## Scope and terminology

- A **Chat Checkpoint** is isolated to one Chat. It has one Current Task and a compact index of completed tasks in that Chat.
- A **Task Transition** occurs only for an explicit independent goal, a new goal after completion, or `/new`. Corrections and incremental requests remain in the Current Task.
- A **Checkpoint Record** is the versioned JSON source of truth. Its Markdown projection remains compatible with the current ReMe memory assembly.
- A **Checkpoint Event Journal** is an append-only, ordered list of deterministic events after the active record's applied event sequence.
- A **Context Epoch** bounds default context eligibility. `/new` and `/clear` start a new epoch; older epochs require explicit user intent to recover. Chat deletion physically deletes its checkpoints, journal, and archive evidence.

## Checkpoint record

The record uses `schema_version`, `checkpoint_id`, `chat_id`, `revision`, `updated_at`, and `confidence` metadata. Its logical fields are:

```text
current_task
  id, title, status, goal[], acceptance_criteria[]
constraints_and_preferences[]
  id, text, kind, source_refs[]
progress
  done[], in_progress[], blocked[]
key_decisions[]
  id, decision, rationale, alternatives_rejected[], evidence_refs[]
next_steps[]
  id, action, preconditions[]
critical_context[]
  fact, certainty, evidence_refs[]
risks_and_unverified[]
evidence_catalog[]
  ref, kind, locator, summary
completed_task_index[]
compaction_state
  archived_through, source_revision, applied_event_sequence
```

Every stateful claim has one or more evidence references. Confirmed facts, inferences, unresolved risks, and planned work remain distinct.

## Model projection

The active ReMe memory interface remains unchanged: the active Checkpoint Record renders to the existing `compressed_summary` string and is supplied through the existing `get_memory()` path.

The Markdown retains the six current sections:

1. Goal, including acceptance criteria;
2. Constraints & Preferences;
3. Progress: Done, In Progress, Blocked;
4. Key Decisions;
5. Next Steps;
6. Critical Context.

Metadata, completed task index, detailed evidence catalog, and inactive risks do not expand by default. A small **Recent Event Delta** follows the projection to describe unincorporated deterministic facts without duplicating raw messages or tool output.

## Event journal

Each new user message, assistant completion, tool-call lifecycle result, file mutation, command exit, test result, evidence recovery, archive boundary, or compaction outcome appends an idempotent event. An event has a unique id, sequence, timestamp, type, whitelisted deterministic facts, and source references. It has no free-form semantic summary or copied tool body.

The active record declares an `applied_event_sequence`. The model context receives only a budget-bounded projection of journal entries after that sequence. At compaction, those entries are incorporated into the next record; events arriving later remain available for the following transaction.

## Context assembly and budgets

The runtime assembles:

```text
permanent context
+ optional long-term memory
+ Checkpoint Record Markdown projection
+ Recent Event Delta
+ budget-selected recent complete interaction units
+ current input
+ evidence recovered only when required
```

The existing `get_memory()` message-list interface remains the integration boundary.

Capacity uses protected reservations plus an elastic pool rather than rigid partitions:

- permanent context occupies its actual, protected size;
- model-output and safety capacity are hard-protected;
- checkpoint projection, recent original interaction, and recovered evidence have caps and compete in the remaining pool according to the Current Task.

Default stage thresholds are calculated from projected next-call usage, including expected model output, tool growth, and safety margin:

| Stage | Default | Action |
| --- | --- | --- |
| Lightweight Governance | 65% | Deduplicate and shrink tool/retrieval material; do not archive conversation history. |
| Active Compaction | 80% | Create a checkpoint update, archive older complete units, and install its projection. |
| Emergency Degradation | 90% or context-limit error | Preserve current input and unpaired tool transactions, use a minimum valid checkpoint if necessary, then retry once. |

The current `memory_compact_ratio` remains migration-compatible as the active-compaction threshold until the staged configuration is introduced.

### Proactive incremental compaction

When predicted usage first reaches 65% of the model window, the runtime queues a non-blocking Precompaction Candidate. It queues a newer candidate after each additional 5% of model-window growth while the active Context Epoch has unincorporated complete interaction units. The candidate derives from a stable record revision and event-sequence snapshot, is fully validated, and remains pending rather than immediately changing online context.

Only one candidate job may run per Chat. Newer trigger watermarks coalesce into the latest snapshot, so a busy Chat does not queue redundant ReMe work. This policy has no elapsed-time trigger.

At the 80% Active Compaction or 90% Emergency Degradation threshold, the runtime installs the newest ready candidate without a new ReMe call when all of the following hold:

- its base Checkpoint Record revision remains active;
- its applied event sequence is a valid prefix of the current journal;
- its source evidence remains durable; and
- installation preserves every message and event after its snapshot.

The runtime then recomputes the budget. If no candidate is valid or installation remains over budget, it falls back to the normal active-compaction path or the emergency minimum-checkpoint path respectively.

Compaction boundaries are complete interaction units. Tool call/result pairs, command/result pairs, approval/actual parameters, file modification/verification pairs, and subtask request/result pairs never split across a boundary. Current user input, latest correction, unfinished transactions, latest errors, and unverified changes remain online.

Tool results continue to use only the existing `tool_result_compact` output budget and recoverable-reference protocol.

## Checkpoint update transaction

Each update is a per-Chat compaction transaction:

```text
capture stable record revision and message/event boundary
→ extract deterministic facts and evidence references
→ ask ReMe for semantic task-state interpretation
→ merge candidate Checkpoint Record
→ validate candidate
→ persist pending candidate
→ durably archive original messages
→ compare revision and atomically activate record + Markdown projection
→ retain concurrent new events and re-evaluate budget
```

Validation rejects candidates that lose current goals, hard constraints, unfinished or blocked items, failed verification, or unpaired tool transactions. It also rejects unsupported status transitions and state claims with no evidence reference.

If semantic generation or validation fails, the online history remains. In emergency mode the runtime can form a deterministic minimum record marked `confidence: degraded`. If archive succeeds but activation fails, the pending record and archive boundary enable idempotent recovery without message loss.

## Evidence recovery

Add an Agent tool conceptually equivalent to:

```text
recover_evidence(refs?, query?, kinds?, time_range?, limit?)
```

The server binds the tool to the requesting tenant, Chat, and active Context Epoch; callers cannot provide a raw `chat_id`, arbitrary file path, or cross-Chat cursor. Exact checkpoint references take precedence over semantic search. Returned data contains source metadata, locator, and only the minimal original fragment needed for the current task.

Archived conversation uses existing hidden-context redaction. Recoverable tool output accepts only references valid under the existing artifact protocol. All recovery output is bounded by the existing `tool_result_compact` configuration. Earlier epochs are never recovered automatically and require explicit user intent.

## Reset and deletion behavior

- `/new` closes the Current Task into the completed-task index and starts a new Context Epoch. Earlier evidence is durable but excluded from default assembly.
- `/clear` resets the active checkpoint and event delta, starts a new epoch, and prevents automatic recovery of prior context. It does not physically delete Chat data.
- Deleting a Chat deletes its checkpoint records, journals, and archived evidence with that Chat.

## Long-term memory

Existing background `summary_memory` continues to write reusable facts and reflections to long-term memory files. It is not a Checkpoint Record source of truth and is never used to reconstruct Chat state.

## Observability and acceptance

Record metrics for projected and actual token usage by segment, budget stage, transaction duration, archived count, revision, validation failures, degraded installs, recovery requests/hits/rejections, and retention of goals, constraints, failures, and unfinished work across repeated compactions.

Required tests include:

1. repeated compaction preserves initial hard constraints, decisions, and unfinished work;
2. boundaries never split protected interaction units;
3. ReMe, validation, archive, and activation failures preserve recoverability;
4. concurrent events are not overwritten by stale snapshots;
5. `/new`, `/clear`, and Chat deletion enforce their epoch/deletion semantics;
6. forged, cross-tenant, cross-Chat, and unauthorized cross-epoch references are rejected;
7. recovered output and ordinary tool output respect `tool_result_compact`;
8. current six-section Markdown projection remains consumable by the existing memory path.
