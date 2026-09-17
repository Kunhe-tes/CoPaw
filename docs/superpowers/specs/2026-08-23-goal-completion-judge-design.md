# Goal Completion Judge Design

## Purpose

Replace first-phase Goal Runtime's command-only deterministic verification with
an independent natural-language completion review. A Goal Contract remains a
user-confirmed, editable natural-language agreement. The Main Agent may propose
completion but may not declare a Goal complete.

## Decisions

- Completion Criteria keep `requirement`, `observable_assertion`,
  `verification_method`, and `expected_outcome` as natural-language fields.
- Contract creation and Direct Goal Edit validate required fields but do not
  require a `command:` verification DSL or an executable Adapter binding.
- A Completion Judge is a separate restricted invocation of the Goal's
  creation-time frozen effective model.
- The Judge receives a Bounded Completion Review Package: active Contract and
  Revision, Main Agent completion proposal and evidence references, relevant
  current-turn tool results, and authorised read-only workspace access.
- The Judge does not receive full Chat history, Main Agent private Plan or
  reasoning, or raw Background SubAgent logs.
- The Judge may use existing read-only tools only, under normal Tool Guard,
  workspace path boundaries, and approval rules. It cannot modify files,
  deploy, run Goal work, alter the Contract, or add/rewrite acceptance
  conditions.
- A Judge accept/reject result is independent of the Main Agent. All mandatory
  Criteria must be accepted before the Goal becomes `COMPLETE`.
- Evidence insufficiency is a rejection. Its recorded reason must name the
  missing evidence.
- Judge tool approval moves the Goal to `WAITING`; resolving it resumes the
  same pending Completion Review Run without a Main Agent turn or budget use.
  Denied approval is a rejection with the approval decision as its reason.
- An externally submitted-but-unresolved approval remains pending; it is not a
  rejection. An approved review tool call is replayed with the complete normal
  Tool Guard payload. A missing replay payload fails closed as a rejection.
- Three consecutive rejections for one Criterion in one Revision move the Goal
  to `BLOCKED`. An accepted review resets that Criterion's rejection count.
- After an environment-writing Main Agent turn, only declared affected Criteria
  are reviewed; if none are declared, all Criteria are reviewed. A
  `propose_completion` reviews all currently unaccepted Criteria.

## Runtime Flow

```text
Main Agent turn
  -> structured Goal Turn Resolution
  -> Goal Runtime settles turn and applies control-command precedence
  -> if relevant Criteria need review:
       Completion Judge receives bounded review package
         -> accept/reject each Criterion
         -> tool approval pending: WAITING; later resume same review
  -> all mandatory Criteria accepted: COMPLETE
  -> otherwise ACTIVE and next Goal turn, subject to budget
```

Direct Goal Edit winning a settlement boundary still discards review of the
previous Revision. A new Revision starts with no accepted Criteria.
It also clears every pending Completion Review approval and retry claim, so an
old Judge invocation cannot review the replacement Contract.

## Architecture

### Goal domain and runtime

Rename the runtime-facing verification vocabulary and types to completion review
without changing the persisted Goal Snapshot field names in this first change:
`verified`, `consecutive_failures`, `evidence_refs`, and
`verification_request_id` retain their storage compatibility but mean accepted
review, consecutive review rejection count, reviewed evidence, and pending
review approval respectively. Update log messages and user-facing state reasons
to say review/rejection rather than deterministic verification/failure.

`GoalRuntime` accepts a `CompletionReviewer` callback with the same asynchronous
shape as the current verifier. It selects Criterion subsets for incremental
review, persists accept/reject or pending approval through the existing service
operations, and alone transitions `COMPLETE`, `WAITING`, and `BLOCKED`.
The Snapshot records the pending Criterion subset and an in-progress retry
claim. Only one retry may claim a pending approval at a time; duplicate wakes
return the current Snapshot rather than counting the same rejection twice.

### Completion Judge invocation

Create a Goal-specific Judge agent factory adjacent to the existing
finalization-agent factory. It copies only request identity required for normal
Tool Guard/approval correlation, freezes the model slot/provider from the
already-resolved Goal Main Agent slot, disables memory, workspace skills, MCP,
SubAgent tools, plan/Goal proposal tools, and all mutating local tools.

The Judge has a fixed system prompt that requires a structured decision for
each supplied Criterion: `accept` or `reject`, a concise reason, and evidence
references. It must state missing evidence on an insufficient-evidence
rejection. The host parses this structured output; malformed/missing output
fails closed as a rejection rather than completing the Goal.

The Judge agent only receives a bounded runtime-built review message. Relevant
tool observations are those produced by the current Main Agent turn and
explicit evidence references; no transcript replay or private planning context
is included.

### Tool and approval boundary

The Judge's toolkit is a dedicated default-deny allowlist of ordinary read-only
built-in tools: `read_file`, `grep_search`, `glob_search`, and
`get_current_time`. Every call continues through existing Tool Guard and
approval handling.
When the guard requires approval, the reviewer returns a pending result carrying
the normal request id. The existing Goal Runtime wait/retry path records it and
reinvokes the same review subset after wake. The reviewer does not execute a
command supplied verbatim by the Contract.

## API and UI

No new user-facing Contract fields are required. The existing editable proposal
and Direct Goal Edit inputs remain natural language. Goal Monitor keeps showing
accepted/remaining Criteria and the latest reason, but labels outcome as
Completion Review rather than Verification where it names the mechanism.

## Testing

- Natural-language Criterion is accepted at create and edit time.
- Main Agent completion proposal requires Judge acceptance before `COMPLETE`.
- Judge rejection preserves `ACTIVE`, persists its reason/evidence, and after
  three consecutive rejections reaches `BLOCKED`.
- An insufficient-evidence Judge result is persisted as a rejection.
- Incremental environment writes only review affected Criteria; undeclared
  affected Criteria recheck all.
- `propose_completion` reviews every unaccepted Criterion.
- Approval pending enters `WAITING`, uses no Main Agent turn, and an approval
  wake retries the same review subset; denied approval records rejection.
- Submitted external approval remains pending; approved hook-mediated tool
  calls retain their Tool Guard replay metadata; a corrupt approved payload
  fails closed.
- Direct Goal Edit while a review approval is pending discards that review;
  concurrent retries of one approval record at most one rejection.
- A pending Direct Goal Edit prevents an old Revision from being reviewed or
  completed.
- Judge construction uses the frozen resolved model and has no write,
  SubAgent, Plan, Goal-control, MCP, memory, or workspace-skill capability.
- Malformed Judge output fails closed and cannot complete a Goal.

## Non-goals

- Guaranteeing objectively repeatable completion proof.
- New user-selectable Judge model configuration.
- New Contract DSL, Adapter registry, task graph, distributed scheduling, or
  cross-instance takeover.
