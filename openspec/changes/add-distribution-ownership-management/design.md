## Context

Cron broadcast children already carry durable provenance in `meta.broadcast_source_job_id`. A source scheduled job can therefore find its children by scanning target-tenant CronManagers for jobs whose metadata points back to the source job ID. Existing broadcast creation also writes target identity into child jobs, so management results can show tenant/user identity without changing the cron model.

Application-market skills are different. The Console already has market skill distribution and recall UI, but this repository does not contain the market backend implementation. The requested owner lookup should not depend on market distribution logs. Instead, the Console will query source users and inspect each user's received skills, matching by stable skill name.

## Goals / Non-Goals

**Goals:**

- Make every scheduled job expose a child lookup action; never hide it only because the job has not been distributed.
- Show an empty child-list state when no broadcast children exist.
- Let managers delete selected child jobs without touching the source job.
- Let managers rerun selected child jobs only when they are enabled; disabled or paused children are skipped and reported as "paused, not executed".
- Rebroadcast to an existing target child refreshes task definition and execution configuration while preserving target identity and enabled/paused state.
- Let application-market managers look up skill owners from each skill's management actions by skill-name matching.
- Include market version and user-side version information in the skill owner lookup.

**Non-Goals:**

- No migration to a centralized cron distribution table.
- No attempt to recover historical skill distribution timestamps.
- No reliance on market distribution log endpoints for skill owner lookup.
- No forced rerun of paused or disabled cron child jobs.

## Decisions

### Use `broadcast_source_job_id` as the cron distribution relationship

The existing child provenance field is enough for reverse lookup and batch actions. This avoids adding a separate index or database table in a code path that is currently file-backed per tenant.

### Rebroadcast updates task definition but preserves target-owned state

When a target already has a child job, rebroadcast should update user-irrelevant execution fields from the source: task content, task type, schedule, runtime, model slot, dispatch mode/meta, and source-derived broadcast metadata. It should preserve child identity and target-owned fields: child job ID, tenant identity, source/scope identity, request user, dispatch target user/session, task chat/session binding, and enabled/paused state.

### Batch rerun skips paused/disabled children

Manual rerun should respect a target user's pause/disable choice. A skipped item remains successful from the batch operation perspective only if the operation itself found and evaluated the child; its item status explicitly says it was skipped.

### Skill owner lookup is a Console aggregation

Because the market backend is outside this repository, the Console can provide the feature by combining source tenant lookup with each tenant's received-skill list. This answers the requested current-state question: "which users have this named skill now?"

## Risks / Trade-offs

- **Risk: tenant scan can be slow with many users** -> keep the UI explicitly loading and show partial failures per user if a user skill query fails.
- **Risk: name matching can produce false positives after manual user edits** -> label the lookup as name-based current ownership and use the stable `skill_name`/market `name`, not display name.
- **Risk: rebroadcast accidentally overwrites target identity** -> isolate the merge helper and cover with regression tests that assert preserved target fields and enabled state.
- **Risk: batch child delete or rerun crosses source scope** -> batch endpoints must verify each selected child still points to the requested source job.

## Open Questions

None. The user confirmed skill lookup belongs in application-market skill management actions, uses name matching, and cron batch rerun skips paused/disabled children.
