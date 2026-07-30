# Chat File Manager Runtime and Performance Design

## Purpose

Improve the Chat File Manager backend without changing its controlled-root
security model, revision-match save contract, or tenant and Agent selection
semantics. The primary goals are to prevent a File Manager request from
starting an Agent runtime and to remove scalability bottlenecks in filesystem
I/O, directory paging, large-file previews, uploads, and archive metadata.

This document supplements `2026-07-29-chat-file-manager-design.md`. It does
not change that document's UI or controlled-directory API scope.

## Decision

File Manager operations resolve an Agent workspace directory directly. They
MUST NOT call `MultiAgentManager.get_agent()` or start `Workspace` runtime.

The request still passes through tenant identity and tenant workspace
middleware. That middleware remains responsible for authenticating the
request, resolving effective tenant/source/scope identity, and ensuring the
minimal tenant bootstrap is available. This decision skips Agent *runtime*
initialization, not tenant isolation or bootstrap.

## Workspace resolution

Introduce a dedicated resolver with a narrow contract:

```python
async def resolve_file_manager_workspace_dir(request: Request) -> Path:
    """Resolve one verified tenant-Agent workspace directory without runtime startup."""
```

It must select the target Agent using the existing precedence:

1. `/api/agents/{agentId}/...` route parameter;
2. `X-Agent-Id` header;
3. the effective tenant configuration's active Agent, falling back to
   `default`.

The resolver loads only the effective tenant-local configuration, finds the
selected enabled profile, and returns its configured `workspace_dir`. It MUST
resolve the path and prove it is a descendant of the effective tenant's
`workspaces/` directory. Missing, disabled, malformed, or out-of-bound
profiles fail closed with the same public status class currently used for an
unknown or unavailable Agent.

The lightweight `request.state.workspace` created by
`TenantWorkspaceMiddleware` is a tenant-root context, not an Agent workspace.
It is a trust anchor for the current tenant only and must not be passed to
`FileManagerService` directly. Passing it directly would expose tenant-level
configuration and sibling Agent workspaces.

All eight File Manager endpoints use this resolver before constructing
`FileManagerService`. The normal console route and Agent-scoped route therefore
address the same directory as before, while a first File Manager request never
calls `Workspace.start()`.

## Request execution model

`FileManagerService` intentionally uses synchronous descriptor-based I/O.
Calling it directly from `async` route handlers can block the event loop during
directory scans, hashing, file copies, and durability syncs. Route handlers
must run those service calls in a bounded worker pool after asynchronous
identity and workspace resolution completes.

The pool is bounded so a burst of archive copies cannot starve unrelated
application work. Archive, restore, and purge operations use a separately
bounded mutation lane; directory, read-preview, upload, and download setup use
the ordinary filesystem lane. Existing per-workspace mutation serialization
continues to protect archive transitions and revision-checked saves.

Download streaming retains its opened no-follow descriptor and cleanup
behavior. It adds `Content-Length` from the opened snapshot. The response must
not reopen a path after authorization, because that would reintroduce a
time-of-check/time-of-use race.

## Directory listing and paging

Today a cursor page scans and stats every direct child, then selects the first
101 natural-sort candidates. Later cursor pages repeat the entire scan. The
new design introduces a bounded in-process directory snapshot cache keyed by:

```text
effective tenant + verified workspace + root + relative path + normalized query
```

A snapshot contains only list metadata: natural-sort keys and item stat data.
It never grants access to a path. Reads, downloads, and mutations continue to
open and validate the target through no-follow descriptors.

Snapshots expire by a short TTL and are invalidated when the cached directory's
identity or modification metadata changes. File Manager uploads, saves,
archives, restores, and purges explicitly invalidate affected parent and
recycle listings. Cache size is globally bounded with LRU eviction, and each
workspace receives a small quota so one large tenant cannot evict every other
tenant's hot directories.

The signed cursor keeps its existing integrity and root/path/query binding. It
also carries a server-generated snapshot version. An expired or invalidated
snapshot produces a restartable pagination conflict, not a silently reordered
or duplicated page. The client refreshes from the first page in that case.

## File preview and text save

For files at or below 1 MiB, preserve the current strict contract: full UTF-8
validation, full SHA-256 revision, and revision-match editing.

For larger files, the result is already read-only. Read at most the preview
limit plus a small multibyte boundary probe, classify based on that bounded
sample, and return a stat-identity revision used only for display/cache
coherence. Do not scan or hash the remaining bytes. The response remains
non-editable.

This deliberately changes one edge case: invalid UTF-8 after the sampled
window can no longer change a large file from a text preview to a binary
preview. This is acceptable only because large-file previews remain
non-editable; the behavior must be documented and covered by tests.

Saving a small text file still performs its two pre-replacement strong revision
checks. After successful replacement it builds the returned preview and
SHA-256 revision from the already-validated encoded body rather than reopening
and rereading the new file.

## Uploads

Replace the whole-body `UploadFile.read(MAX_UPLOAD_BYTES + 1)` flow with a
stream-to-temp-file operation. The worker copies bounded chunks to the existing
no-follow, exclusive temporary destination while maintaining a byte counter.
It rejects and removes the temporary file as soon as the 10 MiB limit is
exceeded. Publication remains link/rename based and never overwrites an
existing destination.

This bounds request-specific memory to the chunk size and preserves collision,
audit, durability, and path-validation semantics.

## Recycle-bin metadata

The existing archive `index.json` is crash recoverable but grows linearly: list,
archive, restore, and purge parse and rewrite the complete item list, and a
single mutation performs several durable transition writes.

Phase one retains the JSON transition protocol and adds pagination to the
recycle response. Phase two migrates archive metadata to a transactional local
store (SQLite in WAL mode is the default choice) with indexes for item ID and
archived time. A migration reads the existing index once, verifies payload
paths, writes a transactionally complete database, and retains the JSON source
until verification completes. Recovery state must remain explicit; removing
intermediate durable states or `fsync` calls is not an acceptable optimization.

## Delivery phases

### Phase 1 — Runtime isolation and event-loop health

- Add the direct File Manager workspace resolver.
- Remove File Manager calls to `get_agent_for_request`.
- Offload synchronous service work to bounded filesystem workers.
- Cache the cursor secret per process.
- Add download `Content-Length` and remove the final save reread.

### Phase 2 — Bounded data paths

- Stream uploads to the controlled temporary file.
- Implement bounded large-file preview classification.
- Add cache invalidation hooks and metrics before enabling directory snapshots.

### Phase 3 — Listing and archive scale

- Enable bounded directory snapshots and snapshot-aware cursor recovery.
- Add recycle-list pagination.
- Migrate archive metadata only when archive size/latency metrics justify it.

Each phase is independently deployable and reversible. Phase 3 does not block
the runtime-startup fix or event-loop isolation work.

## Observability and acceptance criteria

Record histogram and counter metrics tagged by operation and outcome, without
recording paths or file contents:

- workspace-resolution duration and `runtime_start_attempted` (must be zero);
- event-loop worker queue wait and filesystem operation duration;
- directory entries scanned, snapshot hit/miss/invalidation, and cursor restart;
- preview bytes read versus file size;
- upload bytes streamed and size-limit rejection;
- archive index size, recycle page latency, and recovery events.

Acceptance tests must prove:

1. A File Manager request never calls `MultiAgentManager.get_agent()` or
   `Workspace.start()`.
2. Path route, `X-Agent-Id`, and active/default selection resolve exactly as
   before, including effective source/scope tenant identity.
3. Direct resolution cannot access the tenant root, another tenant, or a
   sibling Agent workspace.
4. Link rejection, descriptor validation, revision conflicts, audit records,
   and archive crash recovery continue to pass existing regression tests.
5. A large preview reads no more than its documented bounded sample.
6. A 10k-entry directory can serve subsequent cursor pages from one valid
   snapshot without repeated full scans.
7. Slow filesystem operations do not prevent an unrelated health request from
   completing while a worker is available.

## Out of scope

- Making File Manager a tenant-root filesystem browser.
- Removing tenant bootstrap, identity, source, scope, or Agent selection.
- Weakening no-follow descriptor checks, revision checks, atomic publication,
  archive recovery, or durability confirmation for throughput.
- Cross-process shared directory caches; the initial cache is process-local and
  correctness does not depend on cache coherence.
