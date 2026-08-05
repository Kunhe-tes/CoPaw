# Recycle Listing Complexity Reduction Design

## Goal

Reduce the cognitive complexity of `FileManagerService._list_recycle_items` in
`src/swe/app/file_manager.py` from 21 to 15 or below without changing its
observable directory-listing behaviour.

## Scope

The refactor preserves the recycle root's public response shape, archive-item
validation, ordering, snapshot lifetime and identity checks, cursor validation,
conflict errors, page size, and next-cursor contents. It does not change archive,
restore, purge, or router behaviour.

## Design

Keep `_list_recycle_items` as the orchestration method and extract three focused
private helpers on `FileManagerService`:

1. A helper computes the archive index identity used to validate a saved
   directory snapshot. A missing index retains the `(0, 0, 0)` sentinel.
2. A helper converts one recovered archive-index row into a `FileManagerItem`.
   It validates the ID and original path, parses the timestamp, normalizes the
   size, and returns `None` for malformed rows, preserving the current skip
   behaviour.
3. A helper resolves a snapshot page from a cursor state, validates the snapshot
   version and anchor item, and builds the next cursor when another page exists.
   Invalid, expired, changed, or unanchorable snapshots continue to raise
   `FileManagerConflictError` with the existing message.

For an initial request, the main method builds and sorts valid recycle items,
creates and caches a snapshot, then delegates to the shared pagination helper.
For a cursor request, it delegates directly to that helper. This removes the
duplicated pagination/validation branches while retaining a single ordering
definition: descending archive timestamp and archive ID.

## Error Handling

Malformed archive rows remain invisible rather than failing the listing. Missing
archive indexes remain listable. Cursor and snapshot conflicts remain explicit
refresh-and-retry errors. No archive payload path is exposed by the listing.

## Tests

Retain the existing recycle lifecycle coverage and add focused unit coverage for
malformed archive metadata being skipped and a multi-page recycle listing using
the same stable snapshot and cursor-conflict semantics. Run the focused file
manager tests and the configured complexity check, if present.
