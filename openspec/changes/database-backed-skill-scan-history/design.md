## Context

The SWE skill scanner currently owns history persistence inside its synchronous scanning module. A blocked or warned scan reads the complete `skill_scanner_blocked.json` array, appends one item, and rewrites the file. The management API also returns that complete array, and single deletion identifies an item by its transient array index. The Console then materializes the full response before its Table can paginate it.

CoPaw already initializes one async MySQL-compatible `DatabaseConnection` during the FastAPI lifespan and uses application-scoped stores that create their tables idempotently. The scanner, however, is invoked through synchronous service methods from both the event-loop thread and worker threads, so it cannot directly await that connection. Production is expected to configure the remote database; local deployments without it may continue running with this management capability unavailable.

## Goals / Non-Goals

**Goals:**

- Make the database the sole source of truth for new SWE skill scan alerts.
- Keep synchronous scan call sites fast and preserve block/warn decisions independently of audit persistence health.
- Bound every history response through real database pagination.
- Give each record a stable identity for deterministic deletion.
- Make unavailable storage visible to the API and Console.
- Preserve the current Security page presentation and whitelist behavior outside the history data flow.

**Non-Goals:**

- Importing, reading, renaming, deleting, or otherwise managing legacy `skill_scanner_blocked.json` data.
- Falling back to JSON or another local persistence mechanism.
- Changing scan rules, severity calculation, cache behavior, block/warn semantics, or whitelist storage.
- Adding retention, archival, search, or filtering beyond pagination.
- Changing the separate `market` package's scanner history unless impact analysis shows it is part of the SWE management route.

## Decisions

### Use an application-scoped database store

Add a focused async store backed by the existing `DatabaseConnection`. It will idempotently create a MySQL-compatible history table during application startup and expose insert, count/list page, delete-by-ID, and clear methods. This follows existing SWE store initialization rather than introducing another database client or persistence technology.

The table will contain a stable primary key, skill name, scan timestamp, maximum severity, serialized findings, content hash, and action. A composite index supporting newest-first timestamp/ID traversal will serve the list query. Findings remain structured at the API boundary and are serialized only inside the database column.

Alternatives considered:

- SQLite would work without the remote database but would create a second database system and another per-instance source of truth.
- Keeping JSON behind a paginated API would still require whole-file reads and rewrites and would not solve write amplification.

### Bridge synchronous scans to async persistence with a recorder

Install an application-scoped recorder into the scanner module during FastAPI startup. A synchronous scan constructs the history record and submits it to a bounded in-process queue without awaiting database I/O. Calls made on the application loop enqueue directly; calls from worker threads schedule the enqueue thread-safely onto that loop. One async consumer writes queued records through the store. History reads and mutations flush already-accepted queue work before querying or changing the table so immediate warning checks see the triggering record and clear-all cannot be undone by an older queued insert. Application shutdown also drains accepted records before closing the database connection.

Cross-thread submission reserves bounded queue capacity before reporting success. Each accepted record receives a monotonic sequence and completion is tracked as a contiguous watermark. A `flush()` captures the current accepted sequence as its fence: it waits for every record accepted through that fence, including worker-thread submissions still waiting to enter the event-loop queue, but records accepted after the fence do not prolong that flush. History routes and graceful shutdown apply bounded timeouts so a stalled database insert cannot freeze requests or process termination. Shutdown stops scanner-producing runtime managers before draining the recorder.

If the recorder is absent, its queue is full, or an insert fails, the scanner logs an actionable error and never writes a JSON fallback. The scan's security result remains authoritative: block mode still rejects an unsafe skill and warn mode still follows its configured behavior.

Alternatives considered:

- Blocking synchronous scan paths on `aiomysql` would add database latency to security enforcement and can deadlock when invoked on the application event loop.
- Updating every current and future scan caller to persist separately would duplicate policy and risk missing records.

### Expose one bounded page contract

`GET /config/security/skill-scanner/blocked-history` will require `page` and `page_size` semantics with defaults of 1 and 20, a minimum page size of 10, and a maximum page size of 100. It returns `items`, `total`, `page`, and `page_size`. The store applies `ORDER BY blocked_at DESC, id DESC`, followed by `LIMIT` and `OFFSET`; no API path returns the complete history.

The Console will pass its current page and page size to the endpoint and use the returned `total` for the Table paginator. Deleting or clearing data triggers a bounded refetch and moves to the preceding valid page when the current page becomes empty.

Paginated requests use latest-request-wins semantics so an older response cannot replace a newer page. If concurrent database changes leave the requested page beyond the new final page, the Console clamps to the final valid page and performs one bounded refetch while keeping pagination available.

### Query the latest warning directly for operation feedback

Skill install, import, and broadcast flows need the warning for a specific skill rather than a global history page. Add a database-backed latest-warning lookup ordered by timestamp and stable ID, plus dedicated management endpoints for a server-issued operation cursor and the warning lookup. This is not an unpaginated history or general search interface: it returns at most one warned record for the requested skill created after the cursor captured immediately before the operation. It prevents large or batch operations from losing warning feedback when the matching record falls outside global history page 1, while ensuring a successful current operation cannot surface a historical warning for the same skill.

### Replace positional deletion with stable identity

Each response item includes its database ID. The single-delete route keeps its route location but interprets the final segment as that stable ID rather than a JSON array index. Unknown IDs return 404. Clear-all issues a database delete against the history table.

Because the existing endpoint and Console are deployed together, no compatibility array response or index-delete adapter will be retained.

### Report store unavailability explicitly

History list, delete, and clear routes return HTTP 503 when the database-backed store is not available. They do not return an empty list, because that would incorrectly claim there is no history. The Console keeps the rest of the Security page interactive and presents a history-specific load error.

Write failures are handled separately from management reads: they are logged and observable but do not weaken or change the scanner's enforcement result.

History mutation controls expose an in-progress state and report failures instead of silently closing or leaving users uncertain about the database result.

## Risks / Trade-offs

- **[Queued persistence can lose accepted-but-unflushed records on a hard process crash]** → Drain on graceful shutdown, keep the queue bounded, log rejected/failed writes, and keep scan enforcement independent of persistence.
- **[A stalled database write can prevent a flush from completing]** → Fence each flush to pre-existing accepted work and enforce bounded route and shutdown timeouts with explicit errors and logging.
- **[Concurrent operations on the same skill can share a warning time window]** → Use a server-issued cursor to eliminate historical and client-clock ambiguity; fully isolating simultaneous same-skill operations would require propagating an operation ID through every scanner call and is outside this change.
- **[Offset pagination can shift when new alerts arrive between page requests]** → Use deterministic newest-first ordering; this management history tolerates normal offset movement and does not require cursor snapshots.
- **[The response and deletion contracts are breaking]** → Ship the API and Console changes in the same release and cover both contracts with focused tests.
- **[No-database local environments cannot view or mutate history]** → Return explicit 503 responses and render a localized error without disabling other Security controls.
- **[Old instances may still write JSON during a rolling deployment]** → Treat deployment as an explicit cutover; those JSON-only events are intentionally outside the new history. Do not import them.
- **[Rolling back to the old binary shows stale JSON history and cannot see database rows]** → Preserve the database table and document this visibility limitation; re-deploying the new version restores database history.

## Migration Plan

1. Deploy the idempotent table initialization, recorder lifecycle, database-backed routes, and Console client changes as one release.
2. On startup, create the table and indexes before installing/starting the recorder.
3. Ignore any existing `skill_scanner_blocked.json`; do not inspect, mutate, or migrate it.
4. Verify that a new warned or blocked scan appears through page 1, can be deleted by ID, and that clear-all updates the total.
5. For rollback, deploy the prior application version. Database rows remain intact but are not visible to that version; no reverse migration is performed.

## Open Questions

None. Database-only storage, no JSON migration/fallback, bounded pagination, and non-blocking best-effort audit persistence are agreed boundaries.
