# File Manager Bounded Paths and JSON Listing Design

## Purpose

Complete the remaining File Manager performance work without introducing a
database. This design follows the completed runtime-isolation phase and
supersedes the SQLite/WAL migration proposal in the earlier performance
design.

## Scope

This change delivers three independently testable improvements:

1. stream File Manager uploads into the existing controlled temporary-file
   publication path;
2. bound large-file preview reads and classification; and
3. cache directory and recycle-list snapshots for stable, efficient paging.

The recycle-bin `index.json` remains the sole durable metadata store. There is
no SQLite database, WAL file, schema, migration, or cross-process cache.

## Streaming uploads

The Console route passes the underlying `UploadFile.file` object to a
synchronous File Manager service method running in the existing mutation
worker lane. The service validates the root, directory, and filename before
opening a no-follow exclusive temporary destination. It copies fixed-size
chunks, maintains a byte count, and removes the temporary file immediately on
the first byte beyond the existing 10 MiB limit.

Successful uploads retain the existing no-overwrite, `fsync`, atomic
publication, audit, and `FileManagerItem` response contracts. The source file
object is not retained after the request. Upload buffering is bounded to one
copy chunk plus the framework's own request buffering.

## Bounded large-file previews

Files no larger than the 1 MiB editable limit retain the current full UTF-8
validation and SHA-256 revision behavior. For a larger regular file, the
service reads at most the preview limit plus four bytes to complete or reject a
UTF-8 code point. It never scans or hashes the remainder.

Large previews remain non-editable. Their response revision is a stable
display/cache token constructed from the opened file identity and stat data,
not a content hash. A post-read descriptor identity check still rejects a file
that changed while the bounded sample was read. Invalid UTF-8 after the sample
window cannot alter the read-only classification.

## Snapshot-backed paging

The process-local snapshot cache is bounded by TTL, global LRU capacity, and a
per-workspace entry quota. A snapshot key includes verified workspace path,
root, relative path, and normalized query. It contains only presentation
metadata and natural-sort order; authorization and file reads still use the
existing descriptor-safe paths.

The first page scans and snapshots the listing. Each following cursor names a
signed snapshot version and its last item. The service first validates a cheap
directory/index identity probe, then serves the next page from the snapshot.
If the snapshot expired, was evicted, or its identity changed, it raises a
restartable pagination conflict rather than returning a reordered page.

Working/upload/conversation parent snapshots are invalidated after successful
save, upload, archive, restore, and purge operations. Recycle snapshots are
invalidated after archive, restore, and purge. Entries also expire naturally;
cache correctness never depends on cross-process coherence.

## JSON recycle pagination

Recycle listings accept the same page-size and signed-cursor semantics as
ordinary listings. The first request reads and sorts the recoverable JSON index
into a recycle snapshot; later pages do not repeatedly parse and sort it while
the snapshot is valid. Archive transition recovery and JSON `fsync` behavior
remain unchanged.

## Error handling and observability

- A streamed upload over the size limit returns the existing public 400 error
  and leaves no temporary publication file.
- Invalid snapshot cursors remain 403-style path errors; valid but expired or
  invalidated snapshot cursors return a restartable 409 conflict.
- Metrics record cache hit/miss/eviction/invalidation, entries scanned, cursor
  restarts, preview bytes sampled, and upload bytes copied. They never include
  filenames, paths, content, or tenant identifiers.

## Acceptance criteria

1. Uploading a 10 MiB file never asks `UploadFile` for the complete body and
   publishes byte-for-byte identical content.
2. An over-limit upload stops after at most one additional chunk, leaves no
   temporary file, and preserves the existing audit failure result.
3. A large preview reads no more than the preview limit plus four bytes and is
   non-editable without hashing the unbounded tail.
4. A later page of a 10k-entry directory or recycle index reuses its valid
   snapshot instead of rescanning or reparsing it.
5. A changed directory, archive mutation, cache expiry, or eviction makes the
   old cursor fail with a restartable conflict; it never silently duplicates or
   reorders entries.
6. Existing descriptor checks, revision conflicts, archive recovery, runtime
   isolation, and tenant/Agent workspace selection continue to pass.
